"""Source log system — tracks every data input with tier, reliability, and freshness.

Design:
  - Every prediction run writes a SourceLog listing all its inputs.
  - Post-match: compare source claims vs reality, update reliability scores.
  - The source_registry table stores persistent reliability per source.
"""

from __future__ import annotations
import logging

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ═══════════════════════════════════════════════════════════
#  Tier definitions
# ═══════════════════════════════════════════════════════════
TIER_DEFINITIONS = {
    1: "权威来源（官方 API、俱乐部公告、联赛官网）",
    2: "可信媒体（BBC Sport, The Athletic, Sky Sports）",
    3: "社区/聚合（Transfermarkt, FlashScore, RSS）",
    4: "未验证（社交媒体传闻、单源未确认）",
}

DEFAULT_RELIABILITY = {
    "football-data.org": 0.95,
    "openfootball": 0.85,
    "StatsBomb Open Data": 0.90,
    "Open-Meteo": 0.85,
    "DixonColesModel (internal)": 0.85,
    "TabularEnhancer (internal)": 0.82,
    "EloRatingSystem (internal)": 0.80,
    "IsotonicCalibrator (internal)": 0.85,
    "GDELT": 0.70,
    "RSS feed": 0.65,
    "Event Registry": 0.75,
}


# ═══════════════════════════════════════════════════════════
#  Data structures
# ═══════════════════════════════════════════════════════════
@dataclass(slots=True)
class SourceEntry:
    """One data input used by the prediction."""
    data_name: str           # e.g. "历史比赛数据", "Elo 评分"
    source: str              # e.g. "football-data.org"
    tier: int                # 1-4
    reliability: float       # 0-1, updated after each match
    updated_at: str           # ISO timestamp of last data update
    status: str              # "active", "stale", "unavailable"
    notes: str = ""


@dataclass(slots=True)
class SourceLog:
    """Complete source trace for one prediction run."""
    run_at: str
    match: str
    entries: list[SourceEntry] = field(default_factory=list)

    def active_entries(self) -> list[SourceEntry]:
        return [e for e in self.entries if e.status == "active"]

    def missing_entries(self) -> list[SourceEntry]:
        return [e for e in self.entries if e.status != "active"]

    def reliability_report(self) -> str:
        """Summarize data quality at a glance."""
        active = self.active_entries()
        if not active:
            return "[ERR] No available data"
        tiers = [e.tier for e in active]
        rels = [e.reliability for e in active]
        avg_tier = sum(tiers) / len(tiers)
        avg_rel = sum(rels) / len(rels)
        stale = len([e for e in active if e.status == "stale"])
        return (
            f"数据质量: Tier avg={avg_tier:.1f}  Reliability avg={avg_rel:.2f}  "
            f"活跃源={len(active)} 陈旧={stale} 缺失={len(self.missing_entries())}"
        )


# ═══════════════════════════════════════════════════════════
#  Builder
# ═══════════════════════════════════════════════════════════
class SourceLogBuilder:
    """Build a SourceLog for a prediction run.

    Usage::

        builder = SourceLogBuilder()
        builder.add("历史比赛数据", "football-data.org", tier=1)
        builder.add_missing("首发阵容", "未接入", reason="API未配置")
        log = builder.build("Tottenham vs Leeds")
    """

    def __init__(self) -> None:
        self._entries: list[SourceEntry] = []
        self._now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def add(
        self,
        data_name: str,
        source: str,
        *,
        tier: int | None = None,
        reliability: float | None = None,
        updated_at: str | None = None,
        status: str = "active",
        notes: str = "",
    ) -> SourceLogBuilder:
        if tier is None:
            tier = self._infer_tier(source)
        if reliability is None:
            reliability = DEFAULT_RELIABILITY.get(source, 0.70)
        self._entries.append(SourceEntry(
            data_name=data_name,
            source=source,
            tier=tier,
            reliability=reliability,
            updated_at=updated_at or self._now,
            status=status,
            notes=notes,
        ))
        return self

    def add_missing(self, data_name: str, reason: str) -> SourceLogBuilder:
        self._entries.append(SourceEntry(
            data_name=data_name,
            source="—",
            tier=4,
            reliability=0.0,
            updated_at="—",
            status="unavailable",
            notes=reason,
        ))
        return self

    def build(self, match: str) -> SourceLog:
        return SourceLog(run_at=self._now, match=match, entries=list(self._entries))

    @staticmethod
    def _infer_tier(source: str) -> int:
        if source in ("football-data.org", "StatsBomb Open Data", "Open-Meteo"):
            return 1
        if source in ("openfootball", "GDELT", "Event Registry"):
            return 2
        if source in ("RSS feed",):
            return 3
        if "internal" in source.lower():
            return 1  # Internal models are Tier 1 — we control them
        return 4


# ═══════════════════════════════════════════════════════════
#  Post-match evaluator
# ═══════════════════════════════════════════════════════════
def evaluate_source_accuracy(
    log: SourceLog,
    actual_events: dict[str, bool],
) -> list[dict[str, Any]]:
    """After a match, score each source against what actually happened.

    actual_events: dict of source_name → was_correct (bool)

    Returns list of {source, old_reliability, new_reliability, delta}
    """
    updates = []
    for source_name, was_correct in actual_events.items():
        entry = next((e for e in log.entries if e.source == source_name), None)
        if entry is None:
            continue
        old_rel = entry.reliability
        # Exponential moving average: 90% old + 10% new observation
        new_rel = old_rel * 0.9 + (1.0 if was_correct else 0.0) * 0.1
        updates.append({
            "source": source_name,
            "old_reliability": old_rel,
            "new_reliability": new_rel,
            "delta": new_rel - old_rel,
            "was_correct": was_correct,
        })
    return updates


# ═══════════════════════════════════════════════════════════
#  Markdown renderer
# ═══════════════════════════════════════════════════════════
def render_source_table(log: SourceLog) -> str:
    """Render a Markdown table from a SourceLog."""
    has_notes = any(e.notes for e in log.entries)
    if has_notes:
        lines = [
            "| 数据 | 来源 | Tier | 可靠性 | 状态 | 备注 |",
            "|---|---|---|---|---|---|",
        ]
    else:
        lines = [
            "| 数据 | 来源 | Tier | 可靠性 | 状态 |",
            "|---|---|---|---|---|",
        ]
    for e in log.entries:
        status_icon = {
            "active": "✓",
            "stale": "[WARN] Stale",
            "unavailable": "[WARN] Unavailable",
        }.get(e.status, "?")
        note = e.notes or ""
        if has_notes:
            lines.append(
                f"| {e.data_name} | {e.source} | T{e.tier} | {e.reliability:.2f} | {status_icon} | {note} |"
            )
        else:
            lines.append(
                f"| {e.data_name} | {e.source} | T{e.tier} | {e.reliability:.2f} | {status_icon} |"
            )
    lines.append("")
    lines.append(f"> {log.reliability_report()}")
    return "\n".join(lines)

#!/usr/bin/env python3
"""Single-match prediction via PredictionPipeline (canonical V3.1 entry point).

Replaces the deprecated ``scripts/snapshot.py --home ... --away ...`` with
the unified ``PredictionPipeline``.

Usage::

    python scripts/predict_wc26.py --home "Mexico" --away "South Africa" \\
        --competition "FIFA World Cup 2026" --neutral

Output: backend/reports/{date}_{home}_vs_{away}.md
DB:     Saves to prediction_snapshots (post-match learning compatible).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = BACKEND_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import AsyncSessionLocal
from app.services.dixon_coles import load_training_frame, WC26_FIFA_TIERS
from app.services.prediction_pipeline import PredictionPipeline
from app.services.snapshot_store import save_prediction_snapshot
from app.services.weights import get_weight_config
from app.services.wc_motivation import compute_wc_motivation
from app.models.team import Team
from app.models.manual_event import ManualEvent
from app.models.motivation_event import MotivationEvent, MOTIVATION_TAGS
from sqlalchemy import select, text


# ── Callback: build_team_info ────────────────────────────────────────

async def _build_team_info(db, team_type: str) -> dict[str, dict[str, Any]]:
    """Build team_info mapping for cold-start fallback."""
    result = await db.execute(
        select(Team.name, Team.confederation).where(Team.team_type == team_type)
    )
    rows = result.all()
    team_info: dict[str, dict[str, Any]] = {}
    for name, conf in rows:
        tier = WC26_FIFA_TIERS.get(name, 0)
        team_info[name] = {"confederation": conf or "FIFA", "fifa_tier": tier}
    return team_info


# ── Callback: lookup_venue ───────────────────────────────────────────

async def _lookup_venue(db, home_team: str, away_team: str, competition: str | None = None) -> str | None:
    """Look up stadium from the matches table."""
    try:
        from app.models.match import Match

        home_id_result = await db.execute(
            select(Team.id).where(Team.name.ilike(f"%{home_team}%")).limit(1)
        )
        away_id_result = await db.execute(
            select(Team.id).where(Team.name.ilike(f"%{away_team}%")).limit(1)
        )
        home_id = home_id_result.scalar_one_or_none()
        away_id = away_id_result.scalar_one_or_none()

        if not home_id or not away_id:
            return None

        stmt = (
            select(Match.venue)
            .where(Match.home_team_id == home_id)
            .where(Match.away_team_id == away_id)
            .order_by(Match.match_date.desc())
            .limit(1)
        )
        venue_result = await db.execute(stmt)
        row = venue_result.first()
        return str(row[0]) if row and row[0] else None
    except Exception:
        return None


# ── Callback: lookup_manual_events ───────────────────────────────────

async def _lookup_manual_events(db, team_name: str, limit: int = 5) -> list[dict[str, Any]]:
    """Look up active, unexpired manual events for a team via raw SQL."""
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        stmt = text("""
            SELECT id, team_name, event_type, player_name, severity, confidence,
                   source_name, note, expires_at, created_at
            FROM manual_events
            WHERE team_name LIKE :team_pattern
              AND status = 'active'
            ORDER BY created_at DESC
            LIMIT :limit
        """)
        result = await db.execute(stmt, {"team_pattern": f"%{team_name}%", "limit": limit * 2})
        rows = result.fetchall()

        if not rows:
            return []

        team_id = None
        team_result = await db.execute(select(Team.id).where(Team.name == team_name))
        team_row = team_result.scalar_one_or_none()
        if team_row:
            team_id = str(team_row)

        validated: list[dict[str, Any]] = []
        for row in rows:
            eid, e_team, e_type, e_player, e_sev, e_conf, e_src, e_note, e_expires, e_created = row

            if e_expires and e_expires < now_iso:
                continue

            if e_player and team_id:
                player_result = await db.execute(
                    text("SELECT team_id FROM players WHERE name = :pname"),
                    {"pname": e_player},
                )
                player_team_rows = player_result.fetchall()
                player_team_ids = [str(r[0]) for r in player_team_rows]
                if player_team_ids and team_id not in player_team_ids:
                    continue

            validated.append({
                "event_type": e_type,
                "player": e_player,
                "severity": e_sev,
                "confidence": e_conf,
                "source": e_src,
                "note": e_note,
            })
            if len(validated) >= limit:
                break

        return validated
    except Exception:
        return []


# ── Callback: lookup_match_id ────────────────────────────────────────

async def _lookup_match_id(db, home_team: str, away_team: str) -> str | None:
    """Find match UUID for the predicted fixture."""
    try:
        from app.models.match import Match

        home_id = None
        for query in [
            select(Team.id).where(Team.name == home_team),
            select(Team.id).where(Team.name.ilike(f"%{home_team}%")),
        ]:
            r = await db.execute(query.limit(2))
            rows = r.all()
            if len(rows) == 1:
                home_id = rows[0][0]
                break

        away_id = None
        for query in [
            select(Team.id).where(Team.name == away_team),
            select(Team.id).where(Team.name.ilike(f"%{away_team}%")),
        ]:
            r = await db.execute(query.limit(2))
            rows = r.all()
            if len(rows) == 1:
                away_id = rows[0][0]
                break

        if not home_id or not away_id:
            return None

        stmt = (
            select(Match.id)
            .where(Match.home_team_id == home_id)
            .where(Match.away_team_id == away_id)
            .order_by(Match.match_date.desc())
            .limit(1)
        )
        match_result = await db.execute(stmt)
        row = match_result.first()
        if row:
            return str(row[0]).replace("-", "")
        return None
    except Exception:
        return None


# ── Callback: resolve_team_id ────────────────────────────────────────

async def _resolve_team_id(db, team_name: str):
    """Resolve team name to UUID string."""
    try:
        result = await db.execute(select(Team.id).where(Team.name == team_name))
        row = result.scalar_one_or_none()
        return str(row) if row else None
    except Exception:
        return None


# ── Callback: compute_motivation ─────────────────────────────────────

async def _compute_motivation(db, team_name: str, competition: str) -> dict[str, Any] | None:
    """Compute motivation: WC group-stage priority, fallback to standings events."""
    # World Cup: use group-stage motivation engine
    if "World Cup" in competition:
        wc_motivation = await compute_wc_motivation(db, team_name, competition)
        if wc_motivation:
            return wc_motivation

    # League: use standings-derived motivation tags
    try:
        result = await db.execute(
            select(MotivationEvent)
            .where(MotivationEvent.team_name.ilike(f"%{team_name}%"))
            .order_by(MotivationEvent.created_at.desc())
            .limit(1)
        )
        event = result.scalar_one_or_none()
        if event:
            tag_info = MOTIVATION_TAGS.get(event.motivation_tag, {})
            return {
                "tag": event.motivation_tag,
                "label": tag_info.get("label", event.motivation_tag),
                "strength": event.motivation_strength,
                "explanation": event.explanation,
                "source": event.source,
            }
    except Exception:
        pass
    return None


# ── Report rendering ─────────────────────────────────────────────────

def _render_markdown(snapshot_dict: dict[str, Any]) -> str:
    """Render a minimal Markdown report from the prediction result."""
    lines: list[str] = []

    meta = snapshot_dict.get("meta", {})
    pred = snapshot_dict.get("prediction", {})
    elo_data = snapshot_dict.get("elo", {})
    comp_probs = snapshot_dict.get("component_probs", {})
    params = snapshot_dict.get("pipeline_params", {})

    bp = {"home": pred.get("home_win_prob", 0.33), "draw": pred.get("draw_prob", 0.33), "away": pred.get("away_win_prob", 0.33)}
    xg = {"home": pred.get("home_xg", 0.0), "away": pred.get("away_xg", 0.0)}
    elo = {"home": elo_data.get("home_elo", 0), "away": elo_data.get("away_elo", 0), "gap": elo_data.get("elo_gap", 0)}
    top = pred.get("top_scores", [])
    home = meta.get("home_team", "?")
    away = meta.get("away_team", "?")
    comp = meta.get("competition", "?")
    gen_at = meta.get("generated_at", "?")
    conf = pred.get("confidence", "?")
    degraded = snapshot_dict.get("degraded_reasons", [])

    lines.append(f"# 预测快照：{home} vs {away}")
    lines.append("")
    lines.append(f"> 生成时间：{gen_at}  |  赛事：{comp}")
    mode_str = "degraded" if degraded else "full"
    lines.append(f"> 预测模式：{mode_str}  |  置信度：{conf}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 预测结果")
    lines.append("")
    lines.append(f"| 结果 | 概率 |")
    lines.append(f"|---|---:|")
    lines.append(f"| 主胜 | **{bp.get('home', 0) * 100:.1f}%** |")
    lines.append(f"| 平局 | {bp.get('draw', 0) * 100:.1f}% |")
    lines.append(f"| 客胜 | {bp.get('away', 0) * 100:.1f}% |")
    lines.append("")

    if xg:
        lines.append(f"> 期望进球：{home} **{xg.get('home', 0):.2f}** — **{xg.get('away', 0):.2f}** {away}")
        lines.append("")

    if top:
        lines.append("### Top 3 比分")
        lines.append("")
        for s in top[:3]:
            lines.append(f"- {s.get('score', '?')}（{s.get('prob', 0) * 100:.1f}%）")
        lines.append("")

    if comp_probs:
        lines.append("### 各层独立预测")
        lines.append("")
        lines.append("| 层级 | 主胜 | 平局 | 客胜 |")
        lines.append("|---|---:|---:|---:|")
        for layer, probs in comp_probs.items():
            lines.append(
                f"| {layer} | {probs.get('home', 0) * 100:.1f}% "
                f"| {probs.get('draw', 0) * 100:.1f}% "
                f"| {probs.get('away', 0) * 100:.1f}% |"
            )
        lines.append("")

    if elo:
        lines.append(f"### Elo 评分")
        lines.append(f"- {home}：**{elo.get('home', 0):.0f}**")
        lines.append(f"- {away}：**{elo.get('away', 0):.0f}**")
        lines.append(f"- 评分差：+{elo.get('gap', 0):.0f}")
        lines.append("")

    lines.append("---")
    lines.append(f"> 管线配置：{params.get('config_label', '?')}  |  训练场次：{params.get('training_rows', '?')}")
    lines.append("")

    return "\n".join(lines)


# ── Main entry point ─────────────────────────────────────────────────

async def main(home: str, away: str, competition: str, neutral: bool) -> str:
    """Run prediction via PredictionPipeline and return report path."""
    print(f"\n  WC26 Predict V3.1 — PredictionPipeline", flush=True)
    print(f"  比赛: {home} vs {away} ({competition})", flush=True)

    # Build pipeline with all required callbacks
    pipeline = await PredictionPipeline.from_snapshot_env(
        db_session_factory=AsyncSessionLocal,
        load_training_frame=load_training_frame,
        build_team_info=_build_team_info,
        lookup_venue=_lookup_venue,
        lookup_manual_events=_lookup_manual_events,
        compute_motivation=_compute_motivation,
        lookup_match_id=_lookup_match_id,
        resolve_team_id=_resolve_team_id,
    )

    result = await pipeline.predict_match(
        home_team=home,
        away_team=away,
        competition=competition,
        is_neutral=neutral,
    )

    # ── Lookup match_id ──
    match_id: str | None = None
    try:
        async with AsyncSessionLocal() as db:
            match_id = await _lookup_match_id(db, home, away)
    except Exception:
        pass

    # ── Build dict via PredictionResult.to_dict() (backward-compatible) ──
    snapshot_dict = result.to_dict()
    # Inject match_id into metadata (PredictionResult doesn't know DB ID)
    snapshot_dict["meta"]["match_id"] = match_id or ""

    # ── Save to DB ──
    try:
        await save_prediction_snapshot(snapshot_dict, run_type="manual")
        print(f"  Saved snapshot to DB", flush=True)
    except Exception as exc:
        print(f"  Save snapshot skipped: {exc}", flush=True)

    # ── Render and write report ──
    markdown = _render_markdown(snapshot_dict)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    safe_home = home.replace(" ", "_").replace("/", "-")
    safe_away = away.replace(" ", "_").replace("/", "-")
    report_path = REPORTS_DIR / f"{ts}_{safe_home}_vs_{safe_away}.md"
    report_path.write_text(markdown, encoding="utf-8")

    print(f"  Report: {report_path}", flush=True)

    # Print summary
    print(f"\n  ========================================", flush=True)
    print(f"  {home} vs {away}", flush=True)
    print(f"  H {result.home_win_prob * 100:.1f}% / "
          f"D {result.draw_prob * 100:.1f}% / "
          f"A {result.away_win_prob * 100:.1f}%", flush=True)
    print(f"  xG: {result.home_xg:.2f} - {result.away_xg:.2f}", flush=True)
    if result.degraded_reasons:
        print(f"  Warning — degraded: {len(result.degraded_reasons)} source(s)", flush=True)
        for dr in result.degraded_reasons:
            print(f"    - {dr.source}: {dr.reason}", flush=True)
    print(f"  ========================================", flush=True)

    return str(report_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WC26 PredictionPipeline — single match prediction")
    parser.add_argument("--home", required=True, help="Home team name")
    parser.add_argument("--away", required=True, help="Away team name")
    parser.add_argument("--competition", default="FIFA World Cup 2026", help="Competition name")
    parser.add_argument("--neutral", action="store_true", help="Neutral venue flag")
    args = parser.parse_args()

    asyncio.run(main(args.home, args.away, args.competition, args.neutral))

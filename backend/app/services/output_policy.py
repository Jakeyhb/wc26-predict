"""OutputPolicy — enforces content safety rules based on output mode.

Three modes (from action plan Section 1.2):
  internal_research: Full output — probabilities, market debug, odds data.
  creator_safe:      Creator-friendly — hides odds/betting/bookmaker terms,
                     keeps team analysis, form, schedule, uncertainty.
  public_safe:        Public-compliant — additionally hides probabilities,
                     xG, score predictions. Only rankings, history, info.

Usage:
    from app.services.output_policy import OutputPolicy
    policy = OutputPolicy(mode="creator_safe")
    safe_dict = policy.filter_prediction(prediction_result)
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from app.services.public_safety_filter import (
    CREATOR_SAFE_FORBIDDEN,
    PUBLIC_SAFE_EXTRA_FORBIDDEN,
    scan_text,
)


class OutputMode(str, Enum):
    INTERNAL = "internal_research"
    CREATOR = "creator_safe"
    PUBLIC = "public_safe"


class OutputPolicy:
    """Enforces output content safety based on mode.

    Rules (from action plan Section 8):
    - creator_safe: No odds, betting, bookmaker terms
    - public_safe: Also no probabilities, xG, score predictions
    """

    def __init__(self, mode: str = "internal_research") -> None:
        self.mode = OutputMode(mode)

    # ── Public API ──────────────────────────────────────────

    def filter_text(self, text: str) -> tuple[str, list[str]]:
        """Filter text based on current mode. Returns (safe_text, blocked_terms)."""
        if self.mode == OutputMode.INTERNAL:
            return text, []

        forbidden = self._get_forbidden_terms()
        findings = scan_text(text, forbidden)
        blocked = [f["term"] for f in findings]

        if not blocked:
            return text, []

        # Replace blocked terms with safe alternatives
        safe = text
        replacements = self._get_replacements()
        for term in set(blocked):
            replacement = replacements.get(term.lower(), "[已过滤]")
            safe = safe.replace(term, replacement)

        return safe, blocked

    def filter_prediction(self, result: dict[str, Any]) -> dict[str, Any]:
        """Filter a prediction result dict for the current mode.

        Args:
            result: Prediction result dict (from snapshot.py / PredictionResult.to_dict())

        Returns:
            Filtered dict safe for the current mode.
        """
        if self.mode == OutputMode.INTERNAL:
            return result

        filtered = dict(result)

        # ── creator_safe: strip market/odds fields ──
        if self.mode in (OutputMode.CREATOR, OutputMode.PUBLIC):
            pred = filtered.get("prediction", {})
            if isinstance(pred, dict):
                pred.pop("market_applied", None)
                pred.pop("market_weight_used", None)
                pred.pop("divergence", None)

            # Remove market component probs
            comp = filtered.get("component_probs", {})
            if isinstance(comp, dict):
                comp.pop("market", None)

            # Remove odds_info
            filtered.pop("odds_info", None)
            filtered.pop("market_divergence", None)

        # ── public_safe: additionally strip probabilities/xG/score ──
        if self.mode == OutputMode.PUBLIC:
            pred = filtered.get("prediction", {})
            if isinstance(pred, dict):
                pred.pop("home_win_prob", None)
                pred.pop("draw_prob", None)
                pred.pop("away_win_prob", None)
                pred.pop("home_xg", None)
                pred.pop("away_xg", None)
                pred.pop("top_scores", None)
                pred.pop("score_matrix", None)
                pred.pop("over_under", None)

            # Remove all component probs
            comp = filtered.get("component_probs", {})
            if isinstance(comp, dict):
                for key in list(comp.keys()):
                    comp.pop(key, None)

            # Remove elo probabilities
            elo = filtered.get("elo", {})
            if isinstance(elo, dict):
                elo.pop("detail", None)

        return filtered

    def filter_markdown(self, markdown: str) -> tuple[str, list[str]]:
        """Filter a markdown report for the current mode.

        Returns (safe_markdown, blocked_terms_list).
        """
        return self.filter_text(markdown)

    def audit_artifact(
        self, text: str, artifact_type: str, artifact_path: str = ""
    ) -> dict[str, Any]:
        """Audit a single artifact for compliance.

        Returns audit result dict suitable for output_audit_log table.
        """
        blocked_terms: list[str] = []
        if self.mode != OutputMode.INTERNAL:
            safe_text, blocked = self.filter_text(text)
            blocked_terms = blocked

        return {
            "artifact_type": artifact_type,
            "artifact_path": artifact_path,
            "mode": self.mode.value,
            "passed": len(blocked_terms) == 0,
            "blocked_terms": blocked_terms,
        }

    # ── Helpers ─────────────────────────────────────────────

    def _get_forbidden_terms(self) -> list[str]:
        if self.mode == OutputMode.CREATOR:
            return list(CREATOR_SAFE_FORBIDDEN)
        if self.mode == OutputMode.PUBLIC:
            return list(CREATOR_SAFE_FORBIDDEN) + list(PUBLIC_SAFE_EXTRA_FORBIDDEN)
        return []

    @staticmethod
    def _get_replacements() -> dict[str, str]:
        """Replace forbidden terms with compliant alternatives."""
        return {
            "赔率": "市场参考",
            "盘口": "市场参考",
            "博彩": "[已过滤]",
            "投注": "[已过滤]",
            "博彩公司": "[已过滤]",
            "odds": "market reference",
            "bookmaker": "[filtered]",
            "betting": "[filtered]",
            "handicap": "[filtered]",
            "命中率": "准确度",
            "胜率": "表现",
            "概率": "分析",
            "xG": "期望值",
            "expected goals": "expected value",
            "主胜": "主队",
            "客胜": "客队",
            "平局概率": "平局分析",
            "比分预测": "比赛分析",
            "预计比分": "比赛展望",
        }

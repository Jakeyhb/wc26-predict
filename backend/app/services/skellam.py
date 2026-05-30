"""Skellam draw correction for knockout matches.

In knockout competitions (UCL final/knockout), all Poisson-class models
systematically underestimate draw probability by 3-5 percentage points.
Teams play conservatively, both sides prefer risking penalties to losing.

This module applies an empirically-calibrated draw correction:
  blended_draw = model_draw + knockout_bias

Where knockout_bias is read from postmatch_eval history for knockout matches,
defaulting to +0.03 (conservative) when no history exists.

Reference: Karlis & Ntzoufras (2009) — Skellam distribution theoretical basis.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

DEFAULT_KNOCKOUT_BIAS = 0.03  # Conservative empirical bias for knockout draws


def get_knockout_draw_bias() -> float:
    """Read knockout draw prediction bias from historical evaluation.

    Queries postmatch_eval for knockout-stage matches and computes
    the average (actual_draw - predicted_draw) to use as correction.
    """
    try:
        import sqlite3, os
        db = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data", "local_stage2.db",
        )
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT pe.brier_score, pr.draw_prob,
                   (CASE WHEN pe.actual_result = 'D' THEN 1 ELSE 0 END) as actual_draw
            FROM postmatch_eval pe
            JOIN prediction_runs pr ON pe.prediction_run_id = pr.id
            JOIN matches m ON pr.match_id = m.id
            WHERE m.stage IN ('FINAL', 'SEMI_FINALS', 'QUARTER_FINALS', 'LAST_16')
            ORDER BY pe.created_at DESC
            LIMIT 20
        """).fetchall()
        conn.close()

        if len(rows) >= 5:
            biases = [r["actual_draw"] - r["draw_prob"] for r in rows]
            avg_bias = sum(biases) / len(biases)
            # Clamp to reasonable range
            return max(0.01, min(0.08, avg_bias))
    except Exception:
        pass

    return DEFAULT_KNOCKOUT_BIAS


def apply_skellam_correction(probs, home_xg, away_xg, enabled=False):
    """Apply knockout draw bias correction.

    When enabled: draw += knockout_bias, re-normalize home/away proportionally.
    """
    if not enabled:
        return {**probs, "skellam_applied": False}

    bias = get_knockout_draw_bias()
    new_draw = probs["draw_prob"] + bias

    # Cap: draw can't exceed 45% in knockout (extreme case)
    new_draw = min(new_draw, 0.45)

    remaining = 1.0 - new_draw
    ratio = probs["home_win_prob"] / max(probs["home_win_prob"] + probs["away_win_prob"], 0.01)

    logger.info("Knockout draw correction: +%.1fpp (bias=%.3f)", bias * 100, bias)

    return {
        "home_win_prob": remaining * ratio,
        "draw_prob": new_draw,
        "away_win_prob": remaining * (1.0 - ratio),
        "skellam_applied": True,
        "skellam_correction_pp": bias,
    }

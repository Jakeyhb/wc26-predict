"""score_matrix_calibrator.py — Outcome-Constrained Score Matrix Calibrator.

Rescales a Dixon-Coles score matrix so that its aggregated H/D/A outcome
probabilities match the final fused probabilities.  This fixes the
structural inconsistency where the final H/D/A comes from the full
7-component fusion chain but ``top_scores`` / ``score_matrix`` still
reflects raw DC output.

Mathematical logic
------------------
Let :math:`M[i,j]` be the raw score matrix (shape ``(G+1, G+1)``).

1. Compute bucket sums from the raw matrix:

   .. math::

      P_M^{home} = \\sum_{i>j} M[i,j] \\qquad
      P_M^{draw} = \\sum_{i=j} M[i,j] \\qquad
      P_M^{away} = \\sum_{i<j} M[i,j]

2. Scale each cell by the ratio of target to source bucket probability:

   .. math::

      M'[i,j] = M[i,j] \\times \\frac{P_{target}^{bucket}}{P_M^{bucket}}

3. Normalise: :math:`M'' = M' / \\sum M'`

4. Re-extract top-N scorelines from the calibrated matrix.

Feature flag: ``score_matrix_calibration.enabled`` (default ``True``).
If disabled or an exception occurs, the raw DC matrix is used as-is.

Usage::

    from app.services.score_matrix_calibrator import calibrate_score_matrix

    cal_result = calibrate_score_matrix(
        raw_matrix=dc_score_matrix,
        final_probs={"home_win_prob": 0.45, "draw_prob": 0.25, "away_win_prob": 0.30},
        max_goals=5,
    )
    calibrated_matrix = cal_result["calibrated_matrix"]
    calibrated_top3 = cal_result["top3_scores"]
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ── Feature flag ──────────────────────────────────────────────────────────
# Set to False to bypass calibration and keep raw DC top_scores.
SCORE_MATRIX_CALIBRATION_ENABLED = True


def calibrate_score_matrix(
    raw_matrix: list[list[float]] | np.ndarray,
    final_probs: dict[str, float],
    max_goals: int | None = None,
    eps: float = 1e-12,
) -> dict[str, Any]:
    """Rescale a score matrix so its H/D/A aggregates match *final_probs*.

    Parameters
    ----------
    raw_matrix:
        2-D score matrix, shape ``(max_goals+1, max_goals+1)``, where
        ``raw_matrix[i][j]`` is the probability of home *i*, away *j*.
    final_probs:
        Dict with keys ``home_win_prob``, ``draw_prob``, ``away_win_prob``
        representing the final fused outcome probabilities.
    max_goals:
        Maximum goals per side.  If *None*, inferred from matrix shape.
    eps:
        Floor to prevent division-by-zero in empty buckets.

    Returns
    -------
    dict with keys:
        - ``calibrated_matrix``: 2-D list, same shape as input
        - ``top3_scores``: list of ``{"score": "h:a", "prob": float}``
        - ``before_outcome_probs``: dict with pre-calibration bucket sums
        - ``after_outcome_probs``: dict with post-calibration bucket sums
        - ``target_outcome_probs``: the *final_probs* that were supplied
        - ``outcome_consistency_error``: max abs error vs target (should be < 1e-6)
        - ``max_cell_change_ratio``: largest per-cell scaling factor
        - ``calibration_applied``: bool
    """
    M = np.asarray(raw_matrix, dtype=np.float64)

    if M.ndim != 2 or M.shape[0] != M.shape[1]:
        raise ValueError(
            f"Score matrix must be square, got shape {M.shape}"
        )

    G = max_goals if max_goals is not None else M.shape[0] - 1

    # ── Normalise input in case it drifted ──
    total = M.sum()
    if total <= 0:
        raise ValueError("Score matrix sum is zero — cannot calibrate")
    M = M / total

    # ── Bucket sums (before) ──
    home_mask = np.zeros_like(M, dtype=bool)
    draw_mask = np.zeros_like(M, dtype=bool)
    away_mask = np.zeros_like(M, dtype=bool)
    for i in range(G + 1):
        for j in range(G + 1):
            if i > j:
                home_mask[i, j] = True
            elif i == j:
                draw_mask[i, j] = True
            else:
                away_mask[i, j] = True

    p_home_before = float(M[home_mask].sum())
    p_draw_before = float(M[draw_mask].sum())
    p_away_before = float(M[away_mask].sum())

    # ── Target probabilities ──
    p_home_target = float(final_probs.get("home_win_prob", final_probs.get("home", 0.33)))
    p_draw_target = float(final_probs.get("draw_prob", final_probs.get("draw", 0.33)))
    p_away_target = float(final_probs.get("away_win_prob", final_probs.get("away", 0.33)))

    # ── Per-bucket scaling ──
    M_cal = M.copy()
    if p_home_before > eps:
        M_cal[home_mask] *= p_home_target / p_home_before
    if p_draw_before > eps:
        M_cal[draw_mask] *= p_draw_target / p_draw_before
    if p_away_before > eps:
        M_cal[away_mask] *= p_away_target / p_away_before

    # ── Global re-normalisation ──
    new_total = M_cal.sum()
    if new_total > eps:
        M_cal /= new_total
    else:
        logger.warning("Score matrix calibration produced near-zero total — falling back to raw")
        M_cal = M.copy()

    # ── Bucket sums (after) ──
    p_home_after = float(M_cal[home_mask].sum())
    p_draw_after = float(M_cal[draw_mask].sum())
    p_away_after = float(M_cal[away_mask].sum())

    # ── Diagnostics ──
    consistency_error = max(
        abs(p_home_after - p_home_target),
        abs(p_draw_after - p_draw_target),
        abs(p_away_after - p_away_target),
    )

    # Max per-cell change ratio (avoid div-by-zero)
    safe_M = np.maximum(M, eps)
    cell_ratios = M_cal / safe_M
    max_cell_change = float(np.max(cell_ratios))

    # ── Re-extract top-3 scorelines ──
    top3: list[dict[str, float | str]] = []
    flat = []
    for i in range(G + 1):
        for j in range(G + 1):
            flat.append((i, j, float(M_cal[i, j])))
    for home_g, away_g, prob in sorted(flat, key=lambda x: x[2], reverse=True)[:3]:
        top3.append({"score": f"{home_g}:{away_g}", "prob": round(prob, 4)})

    return {
        "calibrated_matrix": M_cal.tolist(),
        "top3_scores": top3,
        "before_outcome_probs": {
            "home": round(p_home_before, 6),
            "draw": round(p_draw_before, 6),
            "away": round(p_away_before, 6),
        },
        "after_outcome_probs": {
            "home": round(p_home_after, 6),
            "draw": round(p_draw_after, 6),
            "away": round(p_away_after, 6),
        },
        "target_outcome_probs": {
            "home": round(p_home_target, 6),
            "draw": round(p_draw_target, 6),
            "away": round(p_away_target, 6),
        },
        "outcome_consistency_error": round(float(consistency_error), 9),
        "max_cell_change_ratio": round(max_cell_change, 4),
        "calibration_applied": True,
    }

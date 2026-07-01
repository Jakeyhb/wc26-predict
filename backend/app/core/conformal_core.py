"""Pure math for weighted conformal prediction.  No IO, no sklearn.

Implements split-conformal prediction for 3-class (H/D/A) football forecasts
with exponential recency weighting.  All functions are deterministic: same
inputs → same outputs.

References:
  - Stocker et al. (2025). Conformal Time Series Forecasting. arXiv:2511.13608
  - Barber & Pananjady (2025). Conformal prediction under covariate shift.
"""

from __future__ import annotations

import math
from typing import Any

# ── Feature flag ──────────────────────────────────────────────────────────
# Set to True after the calibration set has been built and validated.
WEIGHTED_CONFORMAL_PREDICTION_ENABLED = False

# ── Magic numbers ─────────────────────────────────────────────────────────
CONFORMAL_ALPHA = 0.1                     # miscoverage rate → 90% nominal coverage
CONFORMAL_RECENCY_HALFLIFE_DAYS = 30.0   # exponential weight decay halflife
CONFORMAL_MIN_CALIBRATION_SIZE = 10       # minimum calibration records required


# ═══════════════════════════════════════════════════════════════════════════
#  Nonconformity score
# ═══════════════════════════════════════════════════════════════════════════

def nonconformity_score(prob_true_class: float) -> float:
    """Nonconformity score: 1 − P(true class).

    A perfectly calibrated model would assign P=1.0 → score=0.0.
    A completely wrong model assigns P≈0.0 → score≈1.0.

    Args:
        prob_true_class: Probability the model assigned to the outcome that
            actually occurred, in [0, 1].

    Returns:
        Score in [0, 1].  Lower = more conforming (better calibrated).
    """
    return 1.0 - max(0.0, min(1.0, float(prob_true_class)))


# ═══════════════════════════════════════════════════════════════════════════
#  Recency weighting
# ═══════════════════════════════════════════════════════════════════════════

def recency_weight(
    prediction_time: float,
    calibration_time: float,
    halflife_days: float = CONFORMAL_RECENCY_HALFLIFE_DAYS,
) -> float:
    """Exponential recency weight: w = exp(−λ × Δt).

    The decay constant λ is chosen so that the weight halves after
    *halflife_days*:

        λ = ln(2) / halflife_days

    Args:
        prediction_time: Unix timestamp of the prediction being made.
        calibration_time: Unix timestamp of the calibration observation.
        halflife_days: Days after which weight decays by 50%.

    Returns:
        Weight in (0, 1], where 1.0 = same-day observation.
    """
    delta_seconds = max(0.0, prediction_time - calibration_time)
    delta_days = delta_seconds / 86400.0
    lam = math.log(2) / max(1e-9, halflife_days)
    return math.exp(-lam * delta_days)


# ═══════════════════════════════════════════════════════════════════════════
#  Weighted quantile
# ═══════════════════════════════════════════════════════════════════════════

def _weighted_quantile(
    sorted_scores: list[float],
    sorted_weights: list[float],
    q: float,
) -> float:
    """Compute the weighted quantile of sorted scores.

    Args:
        sorted_scores: Nonconformity scores sorted ascending.
        sorted_weights: Corresponding weights (same order).
        q: Quantile in [0, 1].

    Returns:
        Score threshold at the given weighted quantile.
    """
    if not sorted_scores:
        return 1.0

    total_w = sum(sorted_weights)
    if total_w <= 0:
        return sorted_scores[-1]

    cumulative = 0.0
    target = q * total_w
    for i, w in enumerate(sorted_weights):
        cumulative += w
        if cumulative >= target:
            return sorted_scores[i]
    return sorted_scores[-1]


# ═══════════════════════════════════════════════════════════════════════════
#  Prediction set computation
# ═══════════════════════════════════════════════════════════════════════════

def compute_prediction_set(
    class_probs: list[float],
    calibration_scores: list[float],
    calibration_weights: list[float] | None = None,
    alpha: float = CONFORMAL_ALPHA,
) -> dict[str, Any]:
    """Compute conformal prediction set and calibrated probabilities.

    The prediction set contains all classes whose nonconformity score
    (1 − P(class)) is ≤ the threshold derived from the calibration set.
    Classes within the set are renormalized; classes outside are set to 0.

    Args:
        class_probs: ``[P(H), P(D), P(A)]`` from the underlying model.
        calibration_scores: Nonconformity scores from the calibration set
            (one per historical observation).
        calibration_weights: Optional recency weights matching
            *calibration_scores*.  If ``None``, uniform weights are used.
        alpha: Miscalibration rate (default 0.1 → 90% coverage).

    Returns:
        dict with keys:
          - ``prediction_set``: list[int] of class indices included
          - ``adjusted_probs``: list[float] renormalized within the set
          - ``threshold``: float — the score cutoff
          - ``coverage``: float — nominal 1 − alpha
          - ``set_size``: int — number of classes in the set
    """
    n = len(calibration_scores)
    if n < CONFORMAL_MIN_CALIBRATION_SIZE:
        # Not enough data — return all three classes (uninformative set).
        return {
            "prediction_set": [0, 1, 2],
            "adjusted_probs": [float(p) for p in class_probs],
            "threshold": 1.0,
            "coverage": 1.0 - alpha,
            "set_size": 3,
        }

    # Finite-sample correction: ⌈(n+1)(1−α)⌉ / n
    q_level = min(1.0, math.ceil((n + 1) * (1.0 - alpha)) / n)

    # Sort scores with their weights
    if calibration_weights is None:
        calibration_weights = [1.0] * n

    paired = sorted(zip(calibration_scores, calibration_weights), key=lambda x: x[0])
    sorted_scores = [p[0] for p in paired]
    sorted_weights = [p[1] for p in paired]

    threshold = _weighted_quantile(sorted_scores, sorted_weights, q_level)

    # Build prediction set
    prediction_set: list[int] = []
    adjusted_probs: list[float] = [0.0, 0.0, 0.0]
    for idx, prob in enumerate(class_probs):
        score = nonconformity_score(prob)
        if score <= threshold:
            prediction_set.append(idx)
            adjusted_probs[idx] = prob

    # Safety: guarantee at least one class is always in the set.
    # When the calibration threshold is very tight (e.g. all calibration
    # scores ≈ 0), even the most-probable class may be excluded.  Force-
    # include the class with the lowest nonconformity score.
    if not prediction_set:
        best_idx = max(range(3), key=lambda i: class_probs[i])
        prediction_set.append(best_idx)
        adjusted_probs[best_idx] = class_probs[best_idx]

    # Renormalize within set
    total = sum(adjusted_probs)
    if total > 0:
        adjusted_probs = [p / total for p in adjusted_probs]
    else:
        # Degenerate case: return uniform over the set
        m = len(prediction_set)
        for idx in prediction_set:
            adjusted_probs[idx] = 1.0 / m

    return {
        "prediction_set": prediction_set,
        "adjusted_probs": adjusted_probs,
        "threshold": float(threshold),
        "coverage": 1.0 - alpha,
        "set_size": len(prediction_set),
    }

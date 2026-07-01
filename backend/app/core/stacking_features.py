"""Pure feature engineering for the stacking meta-learner.

Converts per-component probability dicts into a fixed-length feature vector
suitable for multinomial logistic regression.  No IO, no sklearn, no side
effects — follows the core/ purity contract.

Feature vector: 7 components × 3 outcomes (home/draw/away) = 21 floats.
Components are ordered canonically; missing components are filled with a
uniform fallback value.
"""

from __future__ import annotations

from typing import Any

# ── Feature flag ──────────────────────────────────────────────────────────
# Set to True after the meta-learner has been trained and validated on at
# least 20 matches with full component data.
STACKING_META_LEARNER_ENABLED = False

# ── Magic numbers ─────────────────────────────────────────────────────────
STACKING_C = 1.0                # LogisticRegression inverse regularization
STACKING_MAX_ITER = 1000        # solver max iterations
STACKING_MIN_TRAINING_SAMPLES = 20  # minimum samples before fitting
STACKING_FEATURE_FILL = 1.0 / 3.0   # fill value for missing component probs

# Canonical component order.  Must match the order used during training.
STACKING_FEATURE_KEYS: tuple[str, ...] = (
    "dixon_coles",
    "enhancer",
    "negbin",
    "weibull",
    "elo",
    "pi_rating",
    "market",
)

# Per-component outcome keys used when extracting home/draw/away.
_COMPONENT_OUTCOME_ALIASES: dict[str, tuple[str, ...]] = {
    "home": ("home", "home_win", "home_win_prob"),
    "draw": ("draw", "draw_prob"),
    "away": ("away", "away_win", "away_win_prob"),
}

# Market-prob dict uses different key conventions.
_MARKET_OUTCOME_ALIASES: dict[str, tuple[str, ...]] = {
    "home": ("home_prob", "home", "home_win_prob"),
    "draw": ("draw_prob", "draw", "draw_prob"),
    "away": ("away_prob", "away", "away_win_prob"),
}


def _first_key(probs: dict[str, float], aliases: tuple[str, ...], default: float = 1.0 / 3.0) -> float:
    """Return the first matching key's value from *probs*, or *default*."""
    for key in aliases:
        if key in probs:
            return float(probs[key])
    return float(default)


def assemble_feature_vector(
    component_probs: dict[str, dict[str, float]],
    market_probs: dict[str, float] | None = None,
    *,
    missing_fill: float = STACKING_FEATURE_FILL,
) -> list[float]:
    """Build a 21-element feature vector from raw component probabilities.

    Args:
        component_probs: Dict mapping component names (e.g. ``"dixon_coles"``,
            ``"elo"``) to ``{home: float, draw: float, away: float}`` sub-dicts.
        market_probs: Optional market-implied probabilities.  If missing, the
            ``"market"`` slot is filled with *missing_fill* for every outcome.
        missing_fill: Default probability used when a component is absent.

    Returns:
        List of 21 floats in canonical order:
        ``[dc_h, dc_d, dc_a, enh_h, enh_d, enh_a, nb_h, nb_d, nb_a,
          wb_h, wb_d, wb_a, elo_h, elo_d, elo_a, pi_h, pi_d, pi_a,
          mkt_h, mkt_d, mkt_a]``.
    """
    features: list[float] = []

    for comp_key in STACKING_FEATURE_KEYS:
        if comp_key == "market":
            # Market probs may be passed separately or embedded in component_probs.
            src = market_probs if market_probs is not None else component_probs.get("market", {})
            features.append(_first_key(src, _MARKET_OUTCOME_ALIASES["home"], missing_fill))
            features.append(_first_key(src, _MARKET_OUTCOME_ALIASES["draw"], missing_fill))
            features.append(_first_key(src, _MARKET_OUTCOME_ALIASES["away"], missing_fill))
            continue

        comp = component_probs.get(comp_key)
        if comp is None:
            features.extend([missing_fill, missing_fill, missing_fill])
            continue

        features.append(_first_key(comp, _COMPONENT_OUTCOME_ALIASES["home"], missing_fill))
        features.append(_first_key(comp, _COMPONENT_OUTCOME_ALIASES["draw"], missing_fill))
        features.append(_first_key(comp, _COMPONENT_OUTCOME_ALIASES["away"], missing_fill))

    return features


def encode_actual_result(actual_result: str) -> int:
    """Map ``"H"`` / ``"D"`` / ``"A"`` → 0 / 1 / 2.

    Accepts both single-char codes and longer descriptive strings.
    """
    s = (actual_result or "").strip().upper()
    if s in ("H", "HOME", "HOME_WIN", "1"):
        return 0
    if s in ("D", "DRAW", "X", "2"):
        return 1
    if s in ("A", "AWAY", "AWAY_WIN", "3"):
        return 2
    raise ValueError(f"Unknown actual_result: {actual_result!r}")


def build_training_data_from_snapshots(
    snapshots: list[dict[str, Any]],
) -> tuple[list[list[float]], list[int]]:
    """Build (X, y) for stacking from prediction_snapshot DB records.

    Each snapshot dict must contain at least:
      - ``component_probs``: dict of component → {home, draw, away}
      - ``market_probs``: optional market-implied probs
      - ``actual_result``: ``"H"`` / ``"D"`` / ``"A"``

    Snapshots missing ``actual_result`` or ``component_probs`` are silently
    skipped.

    Returns:
        (X, y) where *X* is a list of 21-float vectors and *y* is a list of
        ints (0=home, 1=draw, 2=away).
    """
    X: list[list[float]] = []
    y: list[int] = []

    for snap in snapshots:
        try:
            cp = snap.get("component_probs")
            if not isinstance(cp, dict):
                continue
            actual = snap.get("actual_result")
            if actual is None:
                continue
            mp = snap.get("market_probs")
            feat = assemble_feature_vector(cp, mp if isinstance(mp, dict) else None)
            label = encode_actual_result(str(actual))
            X.append(feat)
            y.append(label)
        except (ValueError, KeyError, TypeError):
            continue

    return X, y

"""PredictionEngine — pure probability fusion, zero IO dependencies.

All functions are deterministic: same inputs → same outputs. No DB, no
network, no file reads, no model loading. This is the single source of truth
for the fusion chain used by CLI, API, and Dashboard paths.

Fusion chain: DC → Enhancer → NegBin → Weibull → Elo → Pi → Market → DrawFloor
"""

from __future__ import annotations

import math

# ── Constants ───────────────────────────────────────────────────

WC_XG_CALIBRATION_FACTOR = 1.35  # WC xG underestimation correction
NEGBIN_R = 3.5  # WC Home Var/Mean=1.42, Away Var/Mean=1.41
NEGBIN_FUSION_WEIGHT = 0.05  # NegBin influence in sequential fusion


# ── NegBin (overdispersion correction) ──────────────────────────

def negbin_pmf(k: int, mu: float, r: float) -> float:
    """Negative Binomial PMF: NB(k; r, p) where p = r/(r+mu)."""
    if mu <= 0:
        return 1.0 if k == 0 else 0.0
    p = r / (r + mu)
    log_prob = r * math.log(p)
    for i in range(k):
        log_prob += math.log(r + i) - math.log(i + 1)
    log_prob += k * math.log(1 - p)
    return math.exp(log_prob)


def overdispersed_scoreline(hxg: float, axg: float, max_g: int = 20) -> dict:
    """NegBin H/D/A probabilities with xG calibration applied.

    Returns dict with 'negbin' (calibrated) and 'poisson' (raw) keys.
    """
    hxg_cal = hxg * WC_XG_CALIBRATION_FACTOR
    axg_cal = axg * WC_XG_CALIBRATION_FACTOR

    # Pure Poisson (raw xG, for comparison)
    pp_h = pp_d = pp_a = 0.0
    for h in range(max_g):
        ph = hxg ** h * math.exp(-hxg) / math.factorial(h)
        for a in range(max_g):
            pa = axg ** a * math.exp(-axg) / math.factorial(a)
            p = ph * pa
            if h > a: pp_h += p
            elif h == a: pp_d += p
            else: pp_a += p

    # Calibrated NegBin
    nb_h = nb_d = nb_a = 0.0
    for h in range(max_g):
        ph = negbin_pmf(h, hxg_cal, NEGBIN_R)
        for a in range(max_g):
            pa = negbin_pmf(a, axg_cal, NEGBIN_R)
            p = ph * pa
            if h > a: nb_h += p
            elif h == a: nb_d += p
            else: nb_a += p

    total_nb = nb_h + nb_d + nb_a
    return {
        "negbin": {"home_win": nb_h / total_nb, "draw": nb_d / total_nb, "away_win": nb_a / total_nb},
        "poisson": {"home_win": pp_h / (pp_h + pp_d + pp_a), "draw": pp_d / (pp_h + pp_d + pp_a), "away_win": pp_a / (pp_h + pp_d + pp_a)},
    }


# ── Fusion helpers ──────────────────────────────────────────────

def fuse_dc_enhancer_adaptive(
    dc_probs: dict[str, float],
    enh_probs: dict[str, float],
    dc_base_weight: float,
) -> tuple[dict[str, float], float, bool, float]:
    """Fuse DC and Enhancer with adaptive divergence guard.

    When DC-Enhancer divergence exceeds 20pp, DC weight is reduced by up to
    0.15 (Enhancer is 0/6 WC direction-correct).  Direction-conflict guard:
    when DC and Enhancer disagree on the favorite, skip weight reduction and
    use normal fusion.

    Args:
        dc_probs: dict with home_win_prob/draw_prob/away_win_prob
        enh_probs: dict with home_win_prob/draw_prob/away_win_prob
        dc_base_weight: base DC weight from weight config (e.g. 0.68)

    Returns:
        (fused_probs, max_divergence_pp, direction_conflict, effective_dc_weight)
    """
    dc_w_ef = float(dc_base_weight)
    # Compute per-outcome divergence
    divs = {}
    for key in ("home_win_prob", "draw_prob", "away_win_prob"):
        divs[key] = abs(dc_probs[key] - enh_probs[key]) * 100
    max_div = float(max(divs.values()))

    dc_fav = max(dc_probs, key=dc_probs.get)
    enh_fav = max(enh_probs, key=enh_probs.get)
    direction_conflict = (dc_fav != enh_fav)

    if max_div > 20 and not direction_conflict:
        shift = min(0.15, (max_div - 20) * 0.015)
        dc_w_ef = max(0.30, dc_base_weight - shift)

    if max_div > 20:
        # Use manual weighted-fusion with adjusted DC weight
        enh_w = 1.0 - dc_w_ef
        fused = {
            k: dc_probs[k] * dc_w_ef + enh_probs[k] * enh_w
            for k in ("home_win_prob", "draw_prob", "away_win_prob")
        }
    else:
        # Normal fusion — call the standard outcome-probability blender
        # (lazy import to avoid circular dependency at module level)
        from app.services.tabular_match_model import fuse_outcome_probabilities
        fused = dict(dc_probs)
        fused.update(fuse_outcome_probabilities(fused, enh_probs, base_weight=dc_base_weight))

    return fused, max_div, direction_conflict, dc_w_ef


def enforce_draw_floor(
    probs: dict[str, float],
    floor: float = 0.12,
) -> tuple[dict[str, float], bool]:
    """Enforce a minimum draw probability floor.

    Deficit allocated 70% from favorite, 30% from underdog.
    Returns (adjusted_probs, was_applied).
    """
    if probs.get("draw_prob", 0) >= floor:
        return dict(probs), False

    deficit = floor - probs["draw_prob"]
    if probs.get("home_win_prob", 0) >= probs.get("away_win_prob", 0):
        probs["home_win_prob"] = max(0.02, probs["home_win_prob"] - deficit * 0.7)
        probs["away_win_prob"] = max(0.02, probs["away_win_prob"] - deficit * 0.3)
    else:
        probs["home_win_prob"] = max(0.02, probs["home_win_prob"] - deficit * 0.3)
        probs["away_win_prob"] = max(0.02, probs["away_win_prob"] - deficit * 0.7)
    probs["draw_prob"] = floor
    total = sum(probs.values())
    return {k: v / total for k, v in probs.items()}, True

"""Pure probability-fusion helpers with zero IO dependencies.

All functions are deterministic: same inputs → same outputs. No DB, no
network, no file reads, no model loading. Shared helpers in this module are
used by the CLI, API, Dashboard, and Tournament Simulator paths.

Fusion chain: DC → Enhancer → NegBin → Weibull → Elo → Pi → Market → DrawFloor
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ── Constants ───────────────────────────────────────────────────

WC_XG_CALIBRATION_FACTOR = 1.35  # WC xG underestimation correction
NEGBIN_R = 3.5  # WC Home Var/Mean=1.42, Away Var/Mean=1.41
NEGBIN_FUSION_WEIGHT = 0.05  # NegBin influence in sequential fusion
MARKET_BOOST_ATTENUATION = 0.60
MARKET_BOOST_DC_ENH_DIVERGENCE_PP = 15.0
MARKET_BOOST_DIVERGENCE_THRESHOLD = 0.15  # model-market divergence triggers boost
MARKET_BOOST_MAX = 0.20  # max additional boost beyond market_max
MARKET_BOOST_SLOPE = 1.0  # boost per pp of divergence above threshold
DRAW_FLOOR = 0.12  # minimum draw probability for WC matches


# ── Dataclasses ─────────────────────────────────────────────────

@dataclass
class CoreFusionResult:
    """Output of run_core_fusion(): DC → Enhancer → NegBin → Weibull → Elo → Pi."""
    probs: dict[str, float]
    dc_enhancer_divergence_pp: float
    dc_enhancer_direction_conflict: bool
    effective_dc_weight: float
    negbin_applied: bool
    weibull_applied: bool


@dataclass
class MarketBoostResult:
    """Output of apply_market_boost(): dynamic market weight adjustment."""
    probs: dict[str, float]
    pre_market_probs: dict[str, float]
    market_applied: bool
    market_weight_used: float
    divergence: float
    boost_attenuated: bool


# ── Internal helpers ────────────────────────────────────────────

def _normalize_triplet(probs: dict[str, float]) -> dict[str, float]:
    """Normalize H/D/A probabilities to sum to 1.  Falls back to uniform (⅓,⅓,⅓).

    Accepts both ``home_win_prob``/``draw_prob``/``away_win_prob`` and
    ``home``/``draw``/``away`` key conventions.
    """
    h = max(0.0, float(probs.get("home_win_prob", probs.get("home", 1 / 3))))
    d = max(0.0, float(probs.get("draw_prob", probs.get("draw", 1 / 3))))
    a = max(0.0, float(probs.get("away_win_prob", probs.get("away", 1 / 3))))
    total = h + d + a
    if total <= 0:
        return {"home_win_prob": 1 / 3, "draw_prob": 1 / 3, "away_win_prob": 1 / 3}
    return {"home_win_prob": h / total, "draw_prob": d / total, "away_win_prob": a / total}


def _blend_component(
    base: dict[str, float],
    component: dict[str, float],
    weight: float,
) -> dict[str, float]:
    """Weighted blend of a component into the base probs, then renormalize.

    Used for Weibull / Elo / Pi sequential fusion steps.
    ``component`` may use either ``home_win_prob``/… or ``home``/… keys.
    """
    key_map = {
        "home_win_prob": ["home_win_prob", "home"],
        "draw_prob": ["draw_prob", "draw"],
        "away_win_prob": ["away_win_prob", "away"],
    }
    result: dict[str, float] = {}
    for k, aliases in key_map.items():
        c_val = base[k]
        for alias in aliases:
            if alias in component:
                c_val = float(component[alias])
                break
        result[k] = base[k] * (1.0 - weight) + c_val * weight
    return _normalize_triplet(result)


def _favorite(probs: dict[str, float]) -> str:
    """Return the key of the largest probability."""
    normalized = {
        "home": float(probs.get("home_win_prob", probs.get("home", 0.0))),
        "draw": float(probs.get("draw_prob", probs.get("draw", 0.0))),
        "away": float(probs.get("away_win_prob", probs.get("away", 0.0))),
    }
    return max(normalized, key=normalized.get)


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
    *,
    consensus_probs: list[dict[str, float]] | None = None,
) -> tuple[dict[str, float], float, bool, float]:
    """Fuse DC and Enhancer with adaptive divergence guard.

    When DC-Enhancer divergence exceeds 20pp, DC weight is reduced by up to
    0.15 (Enhancer is historically unreliable for WC direction).  Direction-
    conflict guard: when DC and Enhancer disagree on the favorite, skip weight
    reduction and use normal fusion.

    V4.3.2 — Consensus gate: when *consensus_probs* (probs from Elo, Pi,
    Weibull, Market) disagree with Enhancer on the favorite AND the
    Enhancer's favorite probability deviates >30pp from the consensus
    median, the Enhancer is fully gated (weight = 0).  This prevents a
    single rogue component from pulling the ensemble toward extreme
    underdog / 3-way-coinflip predictions.

    Args:
        dc_probs: dict with home_win_prob/draw_prob/away_win_prob
        enh_probs: dict with home_win_prob/draw_prob/away_win_prob
        dc_base_weight: base DC weight from weight config (e.g. 0.90)
        consensus_probs: optional list of other component dicts for
            consensus-based Enhancer gating

    Returns:
        (fused_probs, max_divergence_pp, direction_conflict, effective_dc_weight)
    """
    dc_w_ef = float(dc_base_weight)

    # ── V4.3.2 Consensus gate: disable Enhancer when it is an extreme outlier ──
    enhancer_gated = False
    if consensus_probs and len(consensus_probs) >= 2:
        enh_fav_key = max(enh_probs, key=enh_probs.get)
        enh_fav_val = enh_probs[enh_fav_key]
        # Median favorite probability across consensus components
        consensus_vals = sorted(
            comp[enh_fav_key] for comp in consensus_probs
            if enh_fav_key in comp
        )
        if len(consensus_vals) >= 2:
            median_consensus = consensus_vals[len(consensus_vals) // 2]
            if abs(enh_fav_val - median_consensus) > 0.30:
                enhancer_gated = True

    # Compute per-outcome divergence
    divs = {}
    for key in ("home_win_prob", "draw_prob", "away_win_prob"):
        divs[key] = abs(dc_probs[key] - enh_probs[key]) * 100
    max_div = float(max(divs.values()))

    dc_fav = max(dc_probs, key=dc_probs.get)
    enh_fav = max(enh_probs, key=enh_probs.get)
    direction_conflict = (dc_fav != enh_fav)

    if enhancer_gated:
        # Enhancer is an extreme outlier vs consensus — skip entirely
        dc_w_ef = 1.0
    elif max_div > 20 and not direction_conflict:
        shift = min(0.15, (max_div - 20) * 0.015)
        dc_w_ef = max(0.30, dc_base_weight - shift)

    # Always use manual weighted-fusion
    enh_w = 1.0 - dc_w_ef
    fused = _normalize_triplet({
        k: dc_probs[k] * dc_w_ef + enh_probs[k] * enh_w
        for k in ("home_win_prob", "draw_prob", "away_win_prob")
    })

    return fused, max_div, direction_conflict, dc_w_ef


def enforce_draw_floor(
    probs: dict[str, float],
    floor: float = DRAW_FLOOR,
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
    return _normalize_triplet(probs), True


def attenuate_market_boost(
    boost: float,
    *,
    dc_enhancer_divergence_pp: float,
    dc_enhancer_direction_conflict: bool,
    pre_market_probs: dict[str, float],
    market_probs: dict[str, float],
    divergence_threshold_pp: float = MARKET_BOOST_DC_ENH_DIVERGENCE_PP,
    attenuation: float = MARKET_BOOST_ATTENUATION,
) -> tuple[float, bool]:
    """Reduce a dynamic market boost when model consensus is unreliable.

    Attenuation is applied only when all of these conditions hold:
    - DC and Enhancer differ by more than the configured threshold;
    - DC and Enhancer select different most-likely outcomes; and
    - the fused pre-market model and the market select different outcomes.

    The helper accepts either ``home_win_prob``/``draw_prob``/
    ``away_win_prob`` or ``home``/``draw``/``away`` keys.
    """
    if boost <= 0:
        return float(boost), False
    if not 0.0 <= attenuation <= 1.0:
        raise ValueError("attenuation must be between 0 and 1")

    should_attenuate = (
        float(dc_enhancer_divergence_pp) > float(divergence_threshold_pp)
        and bool(dc_enhancer_direction_conflict)
        and _favorite(pre_market_probs) != _favorite(market_probs)
    )
    if not should_attenuate:
        return float(boost), False
    return float(boost) * float(attenuation), True


# ── Unified fusion chain ────────────────────────────────────────

def run_core_fusion(
    *,
    dc_probs: dict[str, float],
    dc_home_xg: float,
    dc_away_xg: float,
    dc_base_weight: float,
    enh_probs: dict[str, float] | None = None,
    weibull_probs: dict[str, float] | None = None,
    weibull_weight: float = 0.0,
    elo_probs: dict[str, float] | None = None,
    elo_weight: float = 0.0,
    pi_probs: dict[str, float] | None = None,
    pi_weight: float = 0.0,
) -> CoreFusionResult:
    """Run the core fusion chain: DC → Enhancer → NegBin → Weibull → Elo → Pi.

    Pure math — no I/O, no side effects.  All component probabilities are
    passed in explicitly.  Callers are responsible for loading models and
    generating component predictions.

    The fusion is *sequential* (not a flat weighted average): each step
    blends its component into the running fused state at its configured
    weight, so early components are diluted by later steps' ``(1 - w)``
    multipliers.

    Returns a ``CoreFusionResult`` with the fused probabilities and
    metadata needed by downstream steps (market boost, draw floor,
    calibration, and learning-engine attribution).
    """
    # ── Step 1: DC baseline ──
    fused = {
        "home_win_prob": float(dc_probs["home_win_prob"]),
        "draw_prob": float(dc_probs["draw_prob"]),
        "away_win_prob": float(dc_probs["away_win_prob"]),
    }

    divergence_pp = 0.0
    direction_conflict = False
    dc_w_ef = dc_base_weight

    # ── Step 2: DC + Enhancer (adaptive, with consensus gate) ──
    if enh_probs is not None:
        # Build consensus list from other available components
        _consensus = []
        for _src in [weibull_probs, elo_probs, pi_probs]:
            if _src is not None:
                _consensus.append({
                    "home_win_prob": float(_src.get("home_win_prob", 0)),
                    "draw_prob": float(_src.get("draw_prob", 0)),
                    "away_win_prob": float(_src.get("away_win_prob", 0)),
                })
        fused, divergence_pp, direction_conflict, dc_w_ef = \
            fuse_dc_enhancer_adaptive(fused, enh_probs, dc_base_weight,
                                      consensus_probs=_consensus if _consensus else None)

    # ── Step 3: NegBin 5% (overdispersion correction) ──
    negbin_applied = False
    if dc_home_xg > 0 and dc_away_xg > 0:
        try:
            od_sl = overdispersed_scoreline(dc_home_xg, dc_away_xg)
            nb_probs = od_sl["negbin"]
            for k in ("home_win_prob", "draw_prob", "away_win_prob"):
                nb_key = {"home_win_prob": "home_win", "draw_prob": "draw", "away_win_prob": "away_win"}[k]
                fused[k] = fused[k] * (1 - NEGBIN_FUSION_WEIGHT) + nb_probs[nb_key] * NEGBIN_FUSION_WEIGHT
            negbin_applied = True
        except Exception:
            pass  # NegBin is best-effort; failure is non-fatal

    # ── Step 4: Weibull ──
    weibull_applied = False
    if weibull_probs is not None and weibull_weight > 0:
        fused = _blend_component(fused, weibull_probs, weibull_weight)
        weibull_applied = True

    # ── Step 5: Elo ──
    if elo_probs is not None and elo_weight > 0:
        fused = _blend_component(fused, elo_probs, elo_weight)

    # ── Step 6: Pi-Rating ──
    if pi_probs is not None and pi_weight > 0:
        fused = _blend_component(fused, pi_probs, pi_weight)

    return CoreFusionResult(
        probs=fused,
        dc_enhancer_divergence_pp=divergence_pp,
        dc_enhancer_direction_conflict=direction_conflict,
        effective_dc_weight=dc_w_ef,
        negbin_applied=negbin_applied,
        weibull_applied=weibull_applied,
    )


def apply_market_boost(
    *,
    fused: dict[str, float],
    market_probs: dict[str, float],
    market_max_weight: float,
    dc_enhancer_divergence_pp: float,
    dc_enhancer_direction_conflict: bool,
    pre_market_probs: dict[str, float] | None = None,
) -> MarketBoostResult:
    """Apply dynamic market boost when model-market divergence exceeds threshold.

    Unified implementation — replaces three inline copies that existed in
    predict_match, predict_sync, and prediction_orchestrator.

    When the model's fused probabilities diverge from market-implied
    probabilities by more than ``MARKET_BOOST_DIVERGENCE_THRESHOLD`` (15pp),
    the market weight is temporarily boosted above ``market_max_weight``.
    The boost is attenuated (×0.6) when DC-Enhancer consensus is unreliable
    (direction conflict + both diverge from market).

    Args:
        fused: Current fused probabilities (after all model components).
        market_probs: Market-implied probabilities (keys: home_prob/draw_prob/away_prob).
        market_max_weight: Base market weight from weight config (e.g. 0.30).
        dc_enhancer_divergence_pp: DC-Enhancer max divergence in percentage points.
        dc_enhancer_direction_conflict: Whether DC and Enhancer disagree on favorite.
        pre_market_probs: Snapshot of fused probs before market (defaults to ``fused``).

    Returns:
        MarketBoostResult with updated probs and metadata.
    """
    snapshot = dict(pre_market_probs) if pre_market_probs is not None else dict(fused)

    model_market_div = max(
        abs(fused.get("home_win_prob", fused.get("home", 0.33)) - market_probs.get("home_prob", 0.5)),
        abs(fused.get("draw_prob", fused.get("draw", 0.33)) - market_probs.get("draw_prob", 0.25)),
        abs(fused.get("away_win_prob", fused.get("away", 0.33)) - market_probs.get("away_prob", 0.25)),
    )

    if model_market_div <= MARKET_BOOST_DIVERGENCE_THRESHOLD:
        return MarketBoostResult(
            probs=dict(fused),
            pre_market_probs=snapshot,
            market_applied=False,
            market_weight_used=market_max_weight,
            divergence=model_market_div,
            boost_attenuated=False,
        )

    # Compute boost
    boost = min(MARKET_BOOST_MAX, (model_market_div - MARKET_BOOST_DIVERGENCE_THRESHOLD) * MARKET_BOOST_SLOPE)
    boost, boost_attenuated = attenuate_market_boost(
        boost,
        dc_enhancer_divergence_pp=dc_enhancer_divergence_pp,
        dc_enhancer_direction_conflict=dc_enhancer_direction_conflict,
        pre_market_probs=snapshot,
        market_probs=market_probs,
    )
    boosted_weight = min(0.50, market_max_weight + boost)

    # Blend
    result = dict(fused)
    result["home_win_prob"] = fused.get("home_win_prob", fused.get("home", 0.33)) * (1 - boosted_weight) \
        + market_probs["home_prob"] * boosted_weight
    result["draw_prob"] = fused.get("draw_prob", fused.get("draw", 0.33)) * (1 - boosted_weight) \
        + market_probs["draw_prob"] * boosted_weight
    result["away_win_prob"] = fused.get("away_win_prob", fused.get("away", 0.33)) * (1 - boosted_weight) \
        + market_probs["away_prob"] * boosted_weight

    result = _normalize_triplet(result)

    return MarketBoostResult(
        probs=result,
        pre_market_probs=snapshot,
        market_applied=True,
        market_weight_used=boosted_weight,
        divergence=model_market_div,
        boost_attenuated=boost_attenuated,
    )

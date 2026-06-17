#!/usr/bin/env python3
"""Reusable full-pipeline prediction: DC -> Enhancer -> Elo -> Pi -> Market -> Signals + Weather.

Usage: python scripts/predict_match_full.py "Saudi Arabia" "Uruguay" "FIFA World Cup 2026"
"""
import sys, json, hashlib, os
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.services.prediction_core import _load_dc, _load_enhancer, _load_elo, _load_pi, _load_training_df
from app.services.prediction_timer import PredictionTimer
from app.services.tabular_match_model import fuse_outcome_probabilities
from app.services.elo_ratings import fuse_elo_probabilities
from app.services.pi_ratings import fuse_pi_probabilities
from app.services.weights import get_weight_config
from app.services.weather_service import WeatherService
from app.services.calibration import IsotonicCalibrator
import math

# ── Overdispersion-corrected NegBin PMF ──
# Pure Poisson has Var=Mean. Actual football: Var≈1.46*Mean (home), 1.38*Mean (away).
# Negative Binomial: Var = μ + μ²/r → r = μ²/(Var-μ)
# From 16,705 matches: r_H ≈ 3.46, r_A ≈ 3.09. Default r=3.0.
NEGBIN_R = 3.0

def negbin_pmf(k: int, mu: float, r: float = NEGBIN_R) -> float:
    """Negative Binomial PMF: NB(k; r, p) where p = r/(r+μ).

    This corrects for overdispersion: tail probabilities are higher than
    pure Poisson, central probabilities are lower. Matches empirical data.
    """
    if mu <= 0:
        return 1.0 if k == 0 else 0.0
    p = r / (r + mu)
    # log P(k) = log(Γ(r+k)) - log(Γ(r)) - log(k!) + r*log(p) + k*log(1-p)
    # Use iterative computation for numerical stability
    log_prob = r * math.log(p)
    for i in range(k):
        log_prob += math.log(r + i) - math.log(i + 1)
    log_prob += k * math.log(1 - p)
    return math.exp(log_prob)

def overdispersed_poisson_scoreline(hxg: float, axg: float, max_g: int = 20) -> dict:
    """Compute H/D/A probabilities using NegBin (corrected for overdispersion).

    Returns both NegBin and pure Poisson results for comparison.
    """
    # Pure Poisson
    pp_h = pp_d = pp_a = 0.0
    for h in range(max_g):
        ph = hxg**h * math.exp(-hxg) / math.factorial(h)
        for a in range(max_g):
            pa = axg**a * math.exp(-axg) / math.factorial(a)
            p = ph * pa
            if h > a: pp_h += p
            elif h == a: pp_d += p
            else: pp_a += p

    # NegBin corrected
    nb_h = nb_d = nb_a = 0.0
    for h in range(max_g):
        ph = negbin_pmf(h, hxg)
        for a in range(max_g):
            pa = negbin_pmf(a, axg)
            p = ph * pa
            if h > a: nb_h += p
            elif h == a: nb_d += p
            else: nb_a += p

    total_nb = nb_h + nb_d + nb_a
    return {
        "poisson": {"home_win": pp_h, "draw": pp_d, "away_win": pp_a},
        "negbin": {"home_win": nb_h / total_nb, "draw": nb_d / total_nb, "away_win": nb_a / total_nb},
        "overdispersion_r": NEGBIN_R,
    }

HOME = sys.argv[1] if len(sys.argv) > 1 else "Saudi Arabia"
AWAY = sys.argv[2] if len(sys.argv) > 2 else "Uruguay"
COMP = sys.argv[3] if len(sys.argv) > 3 else "FIFA World Cup 2026"
IS_NEUTRAL = True
RUN_BOOTSTRAP = "--bootstrap" in sys.argv

timer = PredictionTimer()

# ── Load models ──
dc = _load_dc(timer)
enh = _load_enhancer(timer)
elo = _load_elo(timer)
pi_model = _load_pi(timer)
df = _load_training_df(timer)
wc = get_weight_config(COMP)

# ── 1. DC ──
dc_pred = dc.predict_match(HOME, AWAY, is_neutral_venue=IS_NEUTRAL)
fused = {"home_win_prob": dc_pred["home_win_prob"], "draw_prob": dc_pred["draw_prob"], "away_win_prob": dc_pred["away_win_prob"]}
dc_raw = dict(fused)

# ── 2. Enhancer ──
match_date = df["match_date"].max()
enh_pred = enh.predict_match(home_team=HOME, away_team=AWAY, match_date=match_date,
                              competition_weight=1.0, is_neutral_venue=IS_NEUTRAL, training_df=df)
enh_raw = {"home_win_prob": enh_pred["home_win_prob"], "draw_prob": enh_pred["draw_prob"], "away_win_prob": enh_pred["away_win_prob"]}
fused = fuse_outcome_probabilities(fused, enh_pred, base_weight=wc.dc)
dc_enh = dict(fused)

# ── 2.5. DC-Enhancer Divergence Diagnostic ──
divergence = {}
for outcome, label in [("home_win_prob", "home"), ("draw_prob", "draw"), ("away_win_prob", "away")]:
    div = abs(dc_raw[outcome] - enh_raw[outcome]) * 100
    divergence[label] = round(div, 1)
max_div = max(divergence.values())
divergence["max_pp"] = max_div
if max_div > 15:
    # Determine direction of divergence
    max_outcome = max(divergence, key=lambda k: divergence[k] if k != "max_pp" else 0)
    dc_higher = dc_raw[f"{max_outcome}_win_prob" if max_outcome != "draw" else "draw_prob"] > \
                enh_raw[f"{max_outcome}_win_prob" if max_outcome != "draw" else "draw_prob"]
    divergence["warning"] = (
        f"Large divergence ({max_div:.1f}pp) on {max_outcome}. "
        f"{'DC' if dc_higher else 'Enhancer'} rates this outcome higher. "
        f"Recommend checking DC params and Enhancer features for inconsistencies."
    )
    divergence["severity"] = "high" if max_div > 20 else "medium"
else:
    divergence["warning"] = None
    divergence["severity"] = "normal"

if divergence["warning"]:
    print(f"DIVERGENCE: {divergence['warning']}")

# ── 2.6. Divergence-adaptive DC weight ──
# When DC and Enhancer strongly disagree, DC's marginal contribution is
# most harmful. Reduce DC weight proportionally to divergence.
dc_weight_adaptive = wc.dc
if max_div > 20:
    # Shift up to 0.15 from DC to Enhancer when divergence > 20pp
    shift = min(0.15, (max_div - 20) * 0.015)
    dc_weight_adaptive = wc.dc - shift
    enh_weight_adaptive = 1.0 - dc_weight_adaptive
    print(f"ADAPTIVE: Divergence {max_div:.1f}pp > 20pp threshold. "
          f"DC weight {wc.dc:.2f} → {dc_weight_adaptive:.2f} (shift={shift:.2f})")
    # Recompute DC+Enh fusion with adaptive weights
    fused = {
        "home_win_prob": dc_raw["home_win_prob"] * dc_weight_adaptive + enh_raw["home_win_prob"] * enh_weight_adaptive,
        "draw_prob": dc_raw["draw_prob"] * dc_weight_adaptive + enh_raw["draw_prob"] * enh_weight_adaptive,
        "away_win_prob": dc_raw["away_win_prob"] * dc_weight_adaptive + enh_raw["away_win_prob"] * enh_weight_adaptive,
    }
    dc_enh = dict(fused)
    divergence["dc_weight_adaptive"] = round(dc_weight_adaptive, 2)
    divergence["shift_applied"] = round(shift, 2)
else:
    divergence["dc_weight_adaptive"] = None
    divergence["shift_applied"] = None

# ── 3. Elo ──
elo_obj = elo.predict(HOME, AWAY, is_neutral=IS_NEUTRAL, competition_weight=1.0, competition=COMP)
elo_raw = {"home_win_prob": elo_obj.home_win_prob, "draw_prob": elo_obj.draw_prob, "away_win_prob": elo_obj.away_win_prob}
fused = fuse_elo_probabilities(fused, elo_obj, elo_weight=wc.elo)
dc_enh_elo = dict(fused)

# ── 4. Pi ──
pi_raw_dict = pi_model.predict(HOME, AWAY, IS_NEUTRAL)
pi_raw = {"home_win_prob": pi_raw_dict["home_win_prob"], "draw_prob": pi_raw_dict["draw_prob"], "away_win_prob": pi_raw_dict["away_win_prob"]}
fused = fuse_pi_probabilities(fused, pi_raw, pi_weight=wc.pi)
pre_market = dict(fused)

# ── 5. Market ──
market_raw = None
try:
    from app.services.market.sync_provider import fetch_market_consensus_sync
    market_raw = fetch_market_consensus_sync(HOME, AWAY, COMP, timeout=12.0)
except Exception as e:
    print(f"[MARKET] Error: {e}", file=sys.stderr)

if market_raw and not market_raw.get("degraded"):
    market_home = market_raw["home_prob"]
    market_draw = market_raw["draw_prob"]
    market_away = market_raw["away_prob"]
    market_provider = market_raw["provider"]
    market_live = True
    home_odds = market_raw.get("home_odds", 0)
    draw_odds = market_raw.get("draw_odds", 0)
    away_odds = market_raw.get("away_odds", 0)
else:
    market_home = market_draw = market_away = 0.333
    market_provider = "unavailable"
    market_live = False
    home_odds = draw_odds = away_odds = 0

market_weight = wc.market_max
if market_live:
    fused_market = {
        "home_win_prob": fused["home_win_prob"] * (1 - market_weight) + market_home * market_weight,
        "draw_prob": fused["draw_prob"] * (1 - market_weight) + market_draw * market_weight,
        "away_win_prob": fused["away_win_prob"] * (1 - market_weight) + market_away * market_weight,
    }
    total_m = sum(fused_market.values())
    fused = {k: v / total_m for k, v in fused_market.items()}
post_market = dict(fused)

# ── 6. Signals (will be populated by caller or left default) ──
signals = []
belgium_adj = egypt_adj = 0.0  # reuse variable names for compatibility
signal_home = max(0.01, fused["home_win_prob"])
signal_draw = max(0.01, fused["draw_prob"])
signal_away = max(0.01, fused["away_win_prob"])
total_s = signal_home + signal_draw + signal_away
final = {"home_win_prob": signal_home / total_s, "draw_prob": signal_draw / total_s, "away_win_prob": signal_away / total_s}

# ── 6.5. Probability Calibration (Isotonic Regression) ──
calibrated_final = None
calibration_applied = False
calibration_stats = {"is_fitted": False, "training_samples": 0, "ece": 0.0}
try:
    calibrator = IsotonicCalibrator()
    # Try competition-specific calibrator first, then fall back to generic
    is_wc = "world cup" in COMP.lower()
    cal_name = "calibrator_wc.json" if is_wc else "calibrator.json"
    cal_path = str(BACKEND_DIR / "artifacts" / cal_name)

    # If competition-specific doesn't exist or isn't fitted, fall back
    if not os.path.exists(cal_path) or (is_wc and not Path(cal_path).exists()):
        cal_path = str(BACKEND_DIR / "artifacts" / "calibrator.json")

    calibrator.load(cal_path)
    if calibrator.is_fitted and calibrator.training_sample_count >= 20:
        calibrated_final = calibrator.calibrate(final)
        calibration_applied = True
        calibration_stats = calibrator.calibration_stats()
    elif calibrator.is_fitted:
        print(f"[CALIBRATION] Loaded but only {calibrator.training_sample_count} samples — "
              f"need ≥20. Skipping calibration.", file=sys.stderr)
except Exception as e:
    print(f"[CALIBRATION] Not applied: {e}", file=sys.stderr)

# ── 7. Weather ──
weather_data = {
    "temperature_c": None, "precipitation_mm": 0.0, "wind_speed_kmh": None,
    "humidity_percent": None, "weather_code": None, "weather_description": "unknown",
    "forecast_available": False, "source": "not fetched"
}

# ── Print ──
print(f"DC:        H={dc_raw['home_win_prob']:.4f} D={dc_raw['draw_prob']:.4f} A={dc_raw['away_win_prob']:.4f}")
print(f"Enhancer:  H={enh_raw['home_win_prob']:.4f} D={enh_raw['draw_prob']:.4f} A={enh_raw['away_win_prob']:.4f}")
print(f"DC+Enh:    H={dc_enh['home_win_prob']:.4f} D={dc_enh['draw_prob']:.4f} A={dc_enh['away_win_prob']:.4f}")
print(f"+Elo:      H={dc_enh_elo['home_win_prob']:.4f} D={dc_enh_elo['draw_prob']:.4f} A={dc_enh_elo['away_win_prob']:.4f}")
print(f"+Pi:       H={pre_market['home_win_prob']:.4f} D={pre_market['draw_prob']:.4f} A={pre_market['away_win_prob']:.4f}")
if market_live:
    print(f"+Market:   H={post_market['home_win_prob']:.4f} D={post_market['draw_prob']:.4f} A={post_market['away_win_prob']:.4f}")
print(f"FINAL:     H={final['home_win_prob']:.4f} D={final['draw_prob']:.4f} A={final['away_win_prob']:.4f}")
if calibrated_final:
    print(f"CALIBRATED:H={calibrated_final['home_win_prob']:.4f} D={calibrated_final['draw_prob']:.4f} A={calibrated_final['away_win_prob']:.4f}")

# Overdispersion-corrected scoreline distribution
od_scoreline = overdispersed_poisson_scoreline(dc_pred.get('home_xg', 0), dc_pred.get('away_xg', 0))
print(f"Scoreline: Poisson H={od_scoreline['poisson']['home_win']:.4f} D={od_scoreline['poisson']['draw']:.4f} A={od_scoreline['poisson']['away_win']:.4f}")
print(f"           NegBin  H={od_scoreline['negbin']['home_win']:.4f} D={od_scoreline['negbin']['draw']:.4f} A={od_scoreline['negbin']['away_win']:.4f}")
# Show the difference
for key, label in [("home_win", "H"), ("draw", "D"), ("away_win", "A")]:
    delta = (od_scoreline["negbin"][key] - od_scoreline["poisson"][key]) * 100
    if abs(delta) > 0.3:
        direction = "↑" if delta > 0 else "↓"
        print(f"           NegBin {label} correction: {direction}{abs(delta):.1f}pp")
print(f"xG:        {HOME}={dc_pred.get('home_xg', 0):.2f} {AWAY}={dc_pred.get('away_xg', 0):.2f}")
print(f"Elo:       {HOME}={elo.ratings.get(HOME, 0):.0f} {AWAY}={elo.ratings.get(AWAY, 0):.0f}")
print(f"DC params: {HOME} atk={dc.attack_params.get(HOME, 0):.4f} def={dc.defense_params.get(HOME, 0):.4f}")
print(f"           {AWAY} atk={dc.attack_params.get(AWAY, 0):.4f} def={dc.defense_params.get(AWAY, 0):.4f}")
print(f"Market:    {market_provider} live={market_live} odds=H{home_odds}/D{draw_odds}/A{away_odds}")
print(f"Pi:        {HOME}={pi_model.team_ratings.get(HOME, 0):.2f} {AWAY}={pi_model.team_ratings.get(AWAY, 0):.2f}")

# ── Save ──
dc_params_sorted = json.dumps(sorted(dc.attack_params.items()), sort_keys=True).encode()
result = {
    "home_team": HOME, "away_team": AWAY, "competition": COMP, "is_neutral": IS_NEUTRAL,
    "layers": {"dc": dc_raw, "enhancer": enh_raw, "elo": elo_raw, "pi": pi_raw,
               "dc_enh": dc_enh, "dc_enh_elo": dc_enh_elo, "pre_market": pre_market,
               "post_market": post_market, "final": final},
    "market": {"provider": market_provider, "live": market_live,
               "home_odds": home_odds, "draw_odds": draw_odds, "away_odds": away_odds,
               "home_prob": market_home, "draw_prob": market_draw, "away_prob": market_away,
               "market_weight": market_weight},
    "home_xg": dc_pred.get("home_xg", 0), "away_xg": dc_pred.get("away_xg", 0),
    "elo": {"home": elo.ratings.get(HOME, 0), "away": elo.ratings.get(AWAY, 0)},
    "pi": {"home": pi_model.team_ratings.get(HOME, 0), "away": pi_model.team_ratings.get(AWAY, 0)},
    "dc_params": {"home_atk": dc.attack_params.get(HOME, 0), "home_def": dc.defense_params.get(HOME, 0),
                  "away_atk": dc.attack_params.get(AWAY, 0), "away_def": dc.defense_params.get(AWAY, 0)},
    "calibrated": calibrated_final,
    "calibration_applied": calibration_applied,
    "calibration_stats": calibration_stats,
    "dc_enhancer_divergence": divergence,
    "overdispersion": od_scoreline,
    "bootstrap_ci": None,
    "provenance": {"dc_hash": hashlib.md5(dc_params_sorted).hexdigest()[:12],
                   "dc_teams": len(dc.attack_params), "training_rows": len(df),
                   "version": "3.8.0", "weight_label": wc.label},
}
# ── 8. Bootstrap CI (optional, --bootstrap flag) ──
if RUN_BOOTSTRAP:
    print("\n[Bootstrap] Computing confidence intervals (500 iterations)...")
    try:
        from scripts._bootstrap_ci import bootstrap_lambda_ci
        bs_result = bootstrap_lambda_ci(HOME, AWAY, is_neutral=IS_NEUTRAL, n_bootstrap=500, seed=42)
        if bs_result:
            result["bootstrap_ci"] = {
                "home_win": bs_result["home_win"],
                "draw": bs_result["draw"],
                "away_win": bs_result["away_win"],
                "xg_home": bs_result["bootstrap_xg"]["home"],
                "xg_away": bs_result["bootstrap_xg"]["away"],
                "n_samples": bs_result["n_bootstrap"],
            }
            # Print CI summary
            for key, label in [("home_win", HOME), ("draw", "Draw"), ("away_win", AWAY)]:
                ci = bs_result[key]
                print(f"  {label:20s}: {ci['median']:5.1f}% (95% CI: {ci['ci95_low']:5.1f}% – {ci['ci95_high']:5.1f}%)")
            print(f"  {'xG ' + HOME:20s}: {bs_result['base_xg']['home']:.2f} (95% CI: {bs_result['bootstrap_xg']['home']['ci95_low']:.1f} – {bs_result['bootstrap_xg']['home']['ci95_high']:.1f})")
            print(f"  {'xG ' + AWAY:20s}: {bs_result['base_xg']['away']:.2f} (95% CI: {bs_result['bootstrap_xg']['away']['ci95_low']:.1f} – {bs_result['bootstrap_xg']['away']['ci95_high']:.1f})")
    except Exception as e:
        print(f"  [Bootstrap] Failed: {e}", file=sys.stderr)

out = BACKEND_DIR / "data" / f"_pred_{HOME.replace(' ','_')}_{AWAY.replace(' ','_')}.json"
with open(str(out), "w") as f:
    json.dump(result, f, indent=2, default=str)
print(f"Saved: {out.name}")

#!/usr/bin/env python3
"""Reusable full-pipeline prediction: DC -> Enhancer -> Elo -> Pi -> Market -> Signals + Weather.

Usage: python scripts/predict_match_full.py "Saudi Arabia" "Uruguay" "FIFA World Cup 2026"
"""
import sys, json, hashlib, os, math, io
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# Fix Windows encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app.services.prediction_core import _load_dc, _load_enhancer, _load_elo, _load_pi, _load_training_df
from app.services.prediction_timer import PredictionTimer
from app.services.tabular_match_model import fuse_outcome_probabilities
from app.services.elo_ratings import fuse_elo_probabilities
from app.services.pi_ratings import fuse_pi_probabilities
from app.services.weights import get_weight_config
from app.services.weather_service import WeatherService
from app.services.calibration import IsotonicCalibrator
from app.version import VERSION

# ═══════════════════════════════════════════════════════════════════════════
# World Cup xG Calibration
# ═══════════════════════════════════════════════════════════════════════════
# DC model trained on club football. WC actual avg total goals = 2.81 (n=2,891).
# DC systematically under-predicts xG for national teams: avg 2.02 vs WC 2.81.
# Factor: 2.81/2.02 ≈ 1.39. Initial choice: 1.35.
# V3.9.6: Brazil-Haiti post-match shows both teams' xG overestimated (+74% rel).
# Brazil "early-kill" effect (3 goals in 45min, coast 2H) → calibrate down.
WC_XG_CALIBRATION_FACTOR = 1.20

# ═══════════════════════════════════════════════════════════════════════════
# Overdispersion correction: Negative Binomial
# ═══════════════════════════════════════════════════════════════════════════
# WC: Home Var/Mean=1.42, Away Var/Mean=1.41. NegBin r balances both.
NEGBIN_R = 3.5


def negbin_pmf(k: int, mu: float, r: float) -> float:
    """Negative Binomial PMF: NB(k; r, p) where p = r/(r+mu).

    Corrects for overdispersion: tail probabilities higher than pure Poisson.
    """
    if mu <= 0:
        return 1.0 if k == 0 else 0.0
    p = r / (r + mu)
    log_prob = r * math.log(p)
    for i in range(k):
        log_prob += math.log(r + i) - math.log(i + 1)
    log_prob += k * math.log(1 - p)
    return math.exp(log_prob)


def overdispersed_poisson_scoreline(hxg: float, axg: float, max_g: int = 20) -> dict:
    """Compute H/D/A probabilities + top scorelines with overdispersion correction.

    Returns pure Poisson AND NegBin results for comparison.
    Applies WC xG calibration before NegBin computation.
    """
    hxg_cal = hxg * WC_XG_CALIBRATION_FACTOR
    axg_cal = axg * WC_XG_CALIBRATION_FACTOR

    # Pure Poisson (for comparison, without calibration)
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

    # Top 15 scorelines from NegBin
    scorelines = []
    for h in range(12):
        for a in range(12):
            ph = negbin_pmf(h, hxg_cal, NEGBIN_R)
            pa = negbin_pmf(a, axg_cal, NEGBIN_R)
            scorelines.append((h, a, ph * pa * 100))
    scorelines.sort(key=lambda x: -x[2])

    return {
        "poisson": {"home_win": pp_h, "draw": pp_d, "away_win": pp_a},
        "negbin": {"home_win": nb_h / total_nb, "draw": nb_d / total_nb, "away_win": nb_a / total_nb},
        "overdispersion_r": NEGBIN_R,
        "wc_xg_calibration_factor": WC_XG_CALIBRATION_FACTOR,
        "calibrated_xg": {"home": round(hxg_cal, 2), "away": round(axg_cal, 2)},
        "top_15_scorelines": [{"score": f"{h}-{a}", "prob_pct": round(p, 1)} for h, a, p in scorelines[:15]],
        "under_2_5_pct": round(sum(p for h, a, p in scorelines if h + a < 3), 1),
        "over_2_5_pct": round(sum(p for h, a, p in scorelines if h + a > 2), 1),
    }


def main():
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
    dc_weight_adaptive = wc.dc
    if max_div > 20:
        shift = min(0.15, (max_div - 20) * 0.015)
        dc_weight_adaptive = wc.dc - shift
        enh_weight_adaptive = 1.0 - dc_weight_adaptive
        print(f"ADAPTIVE: Divergence {max_div:.1f}pp > 20pp threshold. "
              f"DC weight {wc.dc:.2f} -> {dc_weight_adaptive:.2f} (shift={shift:.2f})")
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

    # V3.9.5.3: Dynamic market boost when model-market divergence is extreme.
    # When model (pre-market) and market disagree by >15pp on the favorite,
    # the model is likely suffering from component bias (e.g. Enhancer extreme).
    # Boost market_weight up to 0.40 to provide a stronger anchor.
    if market_live:
        model_market_div = max(
            abs(pre_market["home_win_prob"] - market_home),
            abs(pre_market["draw_prob"] - market_draw),
            abs(pre_market["away_win_prob"] - market_away),
        )
        if model_market_div > 0.15:
            # Linear boost: at 15pp divergence → no boost, at 30pp → +0.12
            boost = min(0.12, (model_market_div - 0.15) * 0.8)
            market_weight = min(0.40, wc.market_max + boost)
            print(f"[MARKET_BOOST] model-market divergence={model_market_div:.1%}, "
                  f"market_weight {wc.market_max:.2f}→{market_weight:.2f} (+{boost:.2f})",
                  file=sys.stderr)

    if market_live:
        fused_market = {
            "home_win_prob": fused["home_win_prob"] * (1 - market_weight) + market_home * market_weight,
            "draw_prob": fused["draw_prob"] * (1 - market_weight) + market_draw * market_weight,
            "away_win_prob": fused["away_win_prob"] * (1 - market_weight) + market_away * market_weight,
        }
        total_m = sum(fused_market.values())
        fused = {k: v / total_m for k, v in fused_market.items()}
    post_market = dict(fused)

    # ── 6. Signals ──
    signals = []
    signal_home = max(0.01, fused["home_win_prob"])
    signal_draw = max(0.01, fused["draw_prob"])
    signal_away = max(0.01, fused["away_win_prob"])
    total_s = signal_home + signal_draw + signal_away
    final = {"home_win_prob": signal_home / total_s, "draw_prob": signal_draw / total_s, "away_win_prob": signal_away / total_s}

    # ── 6.5. Probability Calibration ──
    # V3.9.5.3: WC-first, fallback to main calibrator if WC has < 20 samples.
    # calibrator_wc.json auto-activates once ≥20 WC postmatch pairs accumulate.
    calibrated_final = None
    calibration_applied = False
    calibration_stats = {"is_fitted": False, "training_samples": 0, "ece": 0.0}
    try:
        is_wc = "world cup" in COMP.lower()

        # Try WC-specific calibrator first (requires ≥20 WC samples)
        if is_wc:
            wc_path = str(BACKEND_DIR / "artifacts" / "calibrator_wc.json")
            if os.path.exists(wc_path):
                wc_cal = IsotonicCalibrator()
                wc_cal.load(wc_path)
                if wc_cal.is_fitted and wc_cal.training_sample_count >= 20:
                    calibrated_final = wc_cal.calibrate(final)
                    calibration_applied = True
                    calibration_stats = wc_cal.calibration_stats()

        # Fallback: use main calibrator for ALL competitions (including WC)
        # when WC-specific calibrator isn't ready yet
        if not calibration_applied:
            cal_path = str(BACKEND_DIR / "artifacts" / "calibrator.json")
            if os.path.exists(cal_path):
                calibrator = IsotonicCalibrator()
                calibrator.load(cal_path)
                if calibrator.is_fitted and calibrator.training_sample_count >= 20:
                    calibrated_final = calibrator.calibrate(final)
                    calibration_applied = True
                    calibration_stats = calibrator.calibration_stats()
    except Exception:
        pass

    # ── 7. Weather (Open-Meteo API) ──
    weather_data = {
        "temperature_c": None, "precipitation_mm": 0.0, "wind_speed_kmh": None,
        "humidity_percent": None, "weather_code": None, "weather_description": "unknown",
        "forecast_available": False, "source": "not fetched"
    }
    try:
        from app.services.weather_service import WeatherService
        weather_svc = WeatherService()
        weather_data = weather_svc.get_weather_for_match_sync(
            venue=None, home_team=HOME, away_team=AWAY
        )
        if weather_data and weather_data.get("forecast_available"):
            print(f"Weather: {weather_data.get('weather_description', '?')} "
                  f"{weather_data.get('temperature_c', '?')}°C "
                  f"humidity={weather_data.get('humidity_percent', '?')}%")
        else:
            print(f"Weather: unavailable ({weather_data.get('reason', 'no data')})")
    except Exception as e:
        print(f"Weather: error — {e}")

    # ── Output ──
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

    # Overdispersion-corrected scoreline
    od_scoreline = overdispersed_poisson_scoreline(dc_pred.get('home_xg', 0), dc_pred.get('away_xg', 0))
    print(f"Scoreline: Poisson H={od_scoreline['poisson']['home_win']:.4f} D={od_scoreline['poisson']['draw']:.4f} A={od_scoreline['poisson']['away_win']:.4f}")
    print(f"           NegBin  H={od_scoreline['negbin']['home_win']:.4f} D={od_scoreline['negbin']['draw']:.4f} A={od_scoreline['negbin']['away_win']:.4f}")
    for key, label in [("home_win", "H"), ("draw", "D"), ("away_win", "A")]:
        delta = (od_scoreline["negbin"][key] - od_scoreline["poisson"][key]) * 100
        if abs(delta) > 0.3:
            print(f"           NegBin {label} correction: {'+' if delta > 0 else ''}{delta:.1f}pp")

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
                       "version": VERSION, "weight_label": wc.label},
    }

    # ── 8. Bootstrap CI ──
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
                for key, label in [("home_win", HOME), ("draw", "Draw"), ("away_win", AWAY)]:
                    ci = bs_result[key]
                    print(f"  {label:20s}: {ci['median']:5.1f}% (95% CI: {ci['ci95_low']:5.1f}% - {ci['ci95_high']:5.1f}%)")
        except Exception as e:
            print(f"  [Bootstrap] Failed: {e}", file=sys.stderr)

    out = BACKEND_DIR / "data" / f"_pred_{HOME.replace(' ','_')}_{AWAY.replace(' ','_')}.json"
    with open(str(out), "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"Saved: {out.name}")


if __name__ == "__main__":
    main()

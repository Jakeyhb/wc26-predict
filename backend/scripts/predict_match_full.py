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
from app.core.engine import (
    WC_XG_CALIBRATION_FACTOR, NEGBIN_R, NEGBIN_FUSION_WEIGHT,
    negbin_pmf as _negbin_pmf,
    overdispersed_scoreline as _overdispersed_scoreline,
)
from app.services.prediction_timer import PredictionTimer
from app.services.tabular_match_model import fuse_outcome_probabilities
from app.services.elo_ratings import fuse_elo_probabilities
from app.services.pi_ratings import fuse_pi_probabilities
from app.services.weights import get_weight_config
from app.services.weather_service import WeatherService
from app.services.calibration import IsotonicCalibrator
from app.services.weibull_model import WeibullWrapper, fuse_weibull_probs
from app.version import VERSION


def overdispersed_poisson_scoreline(hxg: float, axg: float, max_g: int = 20) -> dict:
    """CLI wrapper: delegates core NegBin computation to shared module,
    then adds display-oriented fields (top scorelines, Over/Under 2.5).
    """
    result = _overdispersed_scoreline(hxg, axg, max_g)
    # Add display-only fields
    hxg_cal = hxg * WC_XG_CALIBRATION_FACTOR
    axg_cal = axg * WC_XG_CALIBRATION_FACTOR
    scorelines = []
    for h in range(12):
        for a in range(12):
            ph = _negbin_pmf(h, hxg_cal, NEGBIN_R)
            pa = _negbin_pmf(a, axg_cal, NEGBIN_R)
            scorelines.append((h, a, ph * pa * 100))
    scorelines.sort(key=lambda x: -x[2])
    result["overdispersion_r"] = NEGBIN_R
    result["wc_xg_calibration_factor"] = WC_XG_CALIBRATION_FACTOR
    result["calibrated_xg"] = {"home": round(hxg_cal, 2), "away": round(axg_cal, 2)}
    result["top_15_scorelines"] = [{"score": f"{h}-{a}", "prob_pct": round(p, 1)} for h, a, p in scorelines[:15]]
    result["under_2_5_pct"] = round(sum(p for h, a, p in scorelines if h + a < 3), 1)
    result["over_2_5_pct"] = round(sum(p for h, a, p in scorelines if h + a > 2), 1)
    return result


def _lookup_wc_stage(home: str, away: str) -> str:
    """Look up the stage for a World Cup match from the schedule DB.

    Returns the stage string (e.g. 'Group A - Matchday 1', 'Round of 16')
    or '' if not found / not a WC match.
    """
    try:
        import sqlite3
        db_path = BACKEND_DIR / "data" / "local_stage2.db"
        if not db_path.exists():
            return ""
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute(
            "SELECT stage FROM wc26_schedule WHERE home_team=? AND away_team=?",
            (home, away),
        )
        row = cur.fetchone()
        conn.close()
        return str(row[0]) if row and row[0] else ""
    except Exception:
        return ""


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
    wc = get_weight_config(COMP, _lookup_wc_stage(HOME, AWAY))

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
    # V4.1.1: direction-conflict guard — when DC and Enhancer disagree
    # on the favorite, skip weight reduction (Enhancer empirically wrong in WC).
    dc_weight_adaptive = wc.dc
    dc_fav_outcome = max(dc_raw, key=dc_raw.get)
    enh_fav_outcome = max(enh_raw, key=enh_raw.get)
    dir_conflict = (dc_fav_outcome != enh_fav_outcome)
    if max_div > 20 and dir_conflict:
        print(f"DIRECTION CONFLICT: DC={dc_fav_outcome} Enhancer={enh_fav_outcome} "
              f"(div={max_div:.1f}pp). Enhancer overridden — keeping DC weight {wc.dc:.2f}")
        divergence["dc_weight_adaptive"] = None
        divergence["shift_applied"] = None
        divergence["direction_conflict"] = True
    elif max_div > 20:
        shift = min(0.15, (max_div - 20) * 0.015)
        dc_weight_adaptive = max(0.30, wc.dc - shift)  # V4.0.5: floor at 0.30 (matching prediction_pipeline.py)
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

    # ── 2.7. NegBin 5% Fusion (V4.3.0: B3) ──
    # Fuse NegBin overdispersed scoreline probabilities into the chain
    # at 5% weight. NegBin corrects Poisson independence assumption by
    # modelling overdispersion (Var/Mean=1.42 for WC matches).
    # Marginal gain ~2%, but fulfills V4.2.1 plan commitment.
    NEGBIN_FUSION_WEIGHT = 0.05
    negbin_probs = None
    negbin_applied = False
    try:
        hxg = dc_pred.get("home_xg", 0)
        axg = dc_pred.get("away_xg", 0)
        if hxg > 0 and axg > 0:
            od_scoreline = overdispersed_poisson_scoreline(hxg, axg)
            negbin_probs = od_scoreline["negbin"]
            # Sequential fusion: NegBin takes 5% of remaining probability space
            fused = {
                "home_win_prob": fused["home_win_prob"] * (1 - NEGBIN_FUSION_WEIGHT) + negbin_probs["home_win"] * NEGBIN_FUSION_WEIGHT,
                "draw_prob": fused["draw_prob"] * (1 - NEGBIN_FUSION_WEIGHT) + negbin_probs["draw"] * NEGBIN_FUSION_WEIGHT,
                "away_win_prob": fused["away_win_prob"] * (1 - NEGBIN_FUSION_WEIGHT) + negbin_probs["away_win"] * NEGBIN_FUSION_WEIGHT,
            }
            negbin_applied = True
    except Exception as e:
        print(f"NegBin:   skipped ({e})")
    dc_enh_nb = dict(fused)

    # ── 2.8. Weibull Copula ──
    # V4.0.3-fix: Weibull was missing from predict_match_full pipeline
    # (weight=0.10 was configured but never applied). Added after DC+Enhancer.
    wb_pred_raw = None
    wb_fitted = False
    try:
        wb = WeibullWrapper()
        wb_fitted = wb.fit(df)
        if wb_fitted:
            wb_pred_raw = wb.predict(HOME, AWAY, IS_NEUTRAL)
            if wb_pred_raw and wb_pred_raw.get("home_win_prob") is not None:
                fused = fuse_weibull_probs(fused, wb_pred_raw, wb_weight=wc.weibull)
                print(f"Weibull:  fitted OK, wb_weight={wc.weibull}")
            else:
                wb_pred_raw = None
    except Exception as e:
        print(f"Weibull:  skipped ({e})")
    dc_enh_wb = dict(fused)

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

    # ── 4.5. Match Importance / Tournament Context ──
    # V4.2.0: Apply motivation adjustment for WC group stage matches.
    # Based on Csató & Gyimesi (2025) six-type classification.
    # Only activates for WC MD3 where strategic behavior is most pronounced.
    is_wc_comp = "world cup" in COMP.lower()
    motivation_result = None
    if is_wc_comp:
        try:
            from app.services.group_standings import GroupStandingsService
            from app.services.match_importance import MatchImportanceCalculator
            standings = GroupStandingsService()
            calc = MatchImportanceCalculator()
            motivation_result = calc.analyze(HOME, AWAY, standings)

            if motivation_result.matchday == 3:
                # Apply motivation adjustments to pre-market probabilities
                home_adj = motivation_result.home_win_adj
                draw_adj = motivation_result.draw_adj
                away_adj = motivation_result.away_win_adj

                fused = {
                    "home_win_prob": max(0.02, fused["home_win_prob"] + home_adj),
                    "draw_prob": max(0.02, fused["draw_prob"] + draw_adj),
                    "away_win_prob": max(0.02, fused["away_win_prob"] + away_adj),
                }
                # Re-normalize
                total = sum(fused.values())
                fused = {k: v / total for k, v in fused.items()}
                pre_market = dict(fused)

                print(f"MOTIVATION: [{motivation_result.match_type.value}] "
                      f"Group {motivation_result.group_name} MD{motivation_result.matchday} | "
                      f"H_motiv={motivation_result.home_motivation:.2f} "
                      f"A_motiv={motivation_result.away_motivation:.2f} | "
                      f"adj: H{home_adj:+.3f} D{draw_adj:+.3f} A{away_adj:+.3f} | "
                      f"collusion={motivation_result.collusion_risk:.2f} "
                      f"rot_H={motivation_result.rotation_risk_home:.2f} "
                      f"rot_A={motivation_result.rotation_risk_away:.2f}")
                if motivation_result.collusion_risk > 0.5:
                    print(f"  ⚠️ COLLUSION RISK: {motivation_result.explanation}")

                # ── Persist MotivationEvent to DB (V4.2.1) ──
                try:
                    import sqlite3 as _sql
                    _db = str(BACKEND_DIR / "data" / "local_stage2.db")
                    _conn = _sql.connect(_db)
                    _match_id = hashlib.md5(
                        f"{HOME}|{AWAY}|{COMP}".encode()
                    ).hexdigest()[:32]
                    _now = datetime.now(timezone.utc).isoformat()
                    for _tname, _motiv, _rot in [
                        (HOME, motivation_result.home_motivation,
                         motivation_result.rotation_risk_home),
                        (AWAY, motivation_result.away_motivation,
                         motivation_result.rotation_risk_away),
                    ]:
                        _tag = ("ROTATION_RISK" if _rot > 0.7 else
                                "HIGH_MOTIVATION" if _motiv >= 0.75 else
                                "MUST_WIN" if _motiv >= 0.60 else
                                "MEDIUM_MOTIVATION" if _motiv >= 0.3 else
                                "LOW_MOTIVATION")
                        _evt_id = hashlib.md5(
                            f"{_match_id}|{_tname}|{_now}".encode()
                        ).hexdigest()[:32]
                        _conn.execute("""
                            INSERT OR REPLACE INTO motivation_events
                                (id, match_id, team_name, motivation_tag,
                                 motivation_strength, explanation, source,
                                 created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            _evt_id, _match_id, _tname, _tag, _motiv,
                            f"{motivation_result.match_type.value} Group "
                            f"{motivation_result.group_name} MD{motivation_result.matchday}",
                            f"WC2026_MD{motivation_result.matchday}",
                            _now, _now,
                        ))
                    _conn.commit()
                    _conn.close()
                except Exception as _exc:
                    print(f"MOTIVATION: DB persist skipped ({_exc})")
            else:
                print(f"MOTIVATION: MD{motivation_result.matchday} — "
                      "context analysis skipped (only MD3 adjustments active)")

        except Exception as exc:
            print(f"MOTIVATION: skipped ({exc})")

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

    # V4.0.3: Dynamic market boost when model-market divergence is extreme.
    # When model (pre-market) and market disagree by >15pp on the favorite,
    # the model is likely suffering from component bias (e.g. Enhancer extreme).
    # Boost market_weight up to 0.50 (raised from 0.40 in V4.0.3).
    # Argentina-Austria: 30.6pp divergence, market_weight 0.40 was correct but
    # borderline. With Enhancer cut to 10%, model should be less biased but
    # when divergence still exceeds 25pp, market deserves more trust.
    if market_live:
        model_market_div = max(
            abs(pre_market["home_win_prob"] - market_home),
            abs(pre_market["draw_prob"] - market_draw),
            abs(pre_market["away_win_prob"] - market_away),
        )
        if model_market_div > 0.15:
            # Linear boost: at 15pp divergence → no boost, at 35pp → +0.20 cap
            boost = min(0.20, (model_market_div - 0.15) * 1.0)
            market_weight = min(0.50, wc.market_max + boost)

            # V4.2.0: Divergence paradox fix — when DC-Enhancer AND
            # Model-Market both diverge in the SAME direction, reduce boost.
            # England-Ghana 0-0: both divergences favored England → double
            # overconfidence. Attenuate by 0.6x when both point same way.
            dc_fav = max(dc_raw, key=dc_raw.get)
            enh_fav = max(enh_raw, key=enh_raw.get)
            market_fav = "home_win_prob" if market_home > max(market_draw, market_away) else (
                "draw_prob" if market_draw > max(market_home, market_away) else "away_win_prob")
            model_fav = max(pre_market, key=pre_market.get)

            dc_enh_diverge = (dc_fav != enh_fav)  # direction conflict between DC and Enhancer
            model_market_diverge = (model_fav != market_fav)  # direction conflict between model and market

            if dc_enh_diverge and model_market_diverge:
                # Both divergences point to market direction → double count risk
                boost *= 0.6
                market_weight = min(0.50, wc.market_max + boost)
                print(f"[MARKET_BOOST] divergence paradox detected — boost attenuated x0.6, "
                      f"market_weight={market_weight:.2f}",
                      file=sys.stderr)

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

    # ── V4.2.0: Draw probability floor ──
    # England-Ghana 0-0: all components underestimated draw (max 22.5%).
    # Structural draw underestimation is a known limitation across all
    # football prediction models (Frontiers 2026 paper). Enforce minimum
    # 12% draw probability for WC matches.
    DRAW_FLOOR = 0.12
    if signal_draw < DRAW_FLOOR:
        deficit = DRAW_FLOOR - signal_draw
        signal_draw = DRAW_FLOOR
        signal_home -= deficit * 0.7
        signal_away -= deficit * 0.3
        # Re-clip to safe minimum
        signal_home = max(0.02, signal_home)
        signal_away = max(0.02, signal_away)

    total_s = signal_home + signal_draw + signal_away
    final = {"home_win_prob": signal_home / total_s, "draw_prob": signal_draw / total_s, "away_win_prob": signal_away / total_s}

    # ── 6.5. Probability Calibration ──
    # V4.1.4: Skip isotonic calibration when market data is available.
    # Market odds ARE the calibration signal — no further isotonic needed.
    # V4.1.5: synced with prediction_pipeline.py (was missing this guard,
    # causing 21-sample calibrator_wc.json to crush draw probabilities to
    # 2-10% and produce duplicate outputs for different inputs).
    calibrated_final = None
    calibration_applied = False
    calibration_stats = {"is_fitted": False, "training_samples": 0, "ece": 0.0}
    cal_reason = "disabled: market data available (market IS calibration)"
    try:
        # ── Skip calibration when market data is present ──
        if market_live:
            calibrator = None
            print(f"Calibration: skipped — market data available")
        else:
            is_wc = "world cup" in COMP.lower()

            # Try WC-specific calibrator first (requires >=50 WC samples)
            if is_wc:
                wc_path = str(BACKEND_DIR / "artifacts" / "calibrator_wc.json")
                if os.path.exists(wc_path):
                    wc_cal = IsotonicCalibrator()
                    wc_cal.load(wc_path)
                    if wc_cal.is_fitted and wc_cal.training_sample_count >= 50:
                        calibrated_final = wc_cal.calibrate(final)
                        calibration_applied = True
                        calibration_stats = wc_cal.calibration_stats()
                        cal_reason = "wc calibrator applied"

            # Fallback: use main calibrator for ALL competitions (including WC)
            # when WC-specific calibrator isn't ready yet (requires >=50 samples)
            if not calibration_applied:
                cal_path = str(BACKEND_DIR / "artifacts" / "calibrator.json")
                if os.path.exists(cal_path):
                    calibrator = IsotonicCalibrator()
                    calibrator.load(cal_path)
                    if calibrator.is_fitted and calibrator.training_sample_count >= 50:
                        calibrated_final = calibrator.calibrate(final)
                        calibration_applied = True
                        calibration_stats = calibrator.calibration_stats()
                        cal_reason = "main calibrator applied"
                    else:
                        cal_reason = (f"calibrator not fitted or {calibrator.training_sample_count} "
                                    f"samples < 50 threshold")
                else:
                    cal_reason = "calibrator.json not found"
    except Exception as exc:
        cal_reason = f"error: {exc}"
        print(f"Calibration: error — {exc}")

    # ── 7. Weather (Open-Meteo API) ──
    # V4.0.3: Always fetch weather for WC matches using venue from schedule DB.
    # Falls back to WeatherService for non-WC / unknown venues.
    weather_data = None
    try:
        from app.services.weather_service import WeatherService
        weather_svc = WeatherService()

        # For World Cup matches, resolve venue from schedule DB for accurate weather
        is_wc_comp = "world cup" in COMP.lower()
        resolved_venue = None
        if is_wc_comp:
            try:
                import sqlite3
                db_path = str(BACKEND_DIR / "data" / "local_stage2.db")
                db = sqlite3.connect(db_path)
                cur = db.cursor()
                cur.execute(
                    """SELECT venue, city FROM wc26_schedule
                       WHERE home_team = ? AND away_team = ?
                       ORDER BY match_date LIMIT 1""",
                    (HOME, AWAY),
                )
                row = cur.fetchone()
                db.close()
                if row:
                    resolved_venue = row[0]
            except Exception:
                pass  # DB lookup best-effort

        weather_data = weather_svc.get_weather_for_match_sync(
            venue=resolved_venue, home_team=HOME, away_team=AWAY
        )
        if weather_data and weather_data.get("forecast_available"):
            print(f"Weather: {weather_data.get('weather_description', '?')} "
                  f"{weather_data.get('temperature_c', '?')}°C "
                  f"humidity={weather_data.get('humidity_percent', '?')}% "
                  f"venue={resolved_venue or 'unknown'}")
        else:
            print(f"Weather: unavailable (venue={resolved_venue or 'unknown'}, "
                  f"reason={weather_data.get('reason', 'no data') if weather_data else 'fetch failed'})")
    except Exception as e:
        print(f"Weather: error — {e}")
        weather_data = {
            "temperature_c": None, "precipitation_mm": 0.0, "wind_speed_kmh": None,
            "humidity_percent": None, "weather_code": None, "weather_description": "unknown",
            "forecast_available": False, "source": "fetch_error"
        }

    # ── Output ──
    print(f"DC:        H={dc_raw['home_win_prob']:.4f} D={dc_raw['draw_prob']:.4f} A={dc_raw['away_win_prob']:.4f}")
    print(f"Enhancer:  H={enh_raw['home_win_prob']:.4f} D={enh_raw['draw_prob']:.4f} A={enh_raw['away_win_prob']:.4f}")
    print(f"DC+Enh:    H={dc_enh['home_win_prob']:.4f} D={dc_enh['draw_prob']:.4f} A={dc_enh['away_win_prob']:.4f}")
    if negbin_applied:
        print(f"+NegBin:   H={dc_enh_nb['home_win_prob']:.4f} D={dc_enh_nb['draw_prob']:.4f} A={dc_enh_nb['away_win_prob']:.4f}")
    if wb_pred_raw:
        print(f"+Weibull:  H={dc_enh_wb['home_win_prob']:.4f} D={dc_enh_wb['draw_prob']:.4f} A={dc_enh_wb['away_win_prob']:.4f}")
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
        "layers": {"dc": dc_raw, "enhancer": enh_raw, "negbin": negbin_probs, "weibull": wb_pred_raw, "elo": elo_raw, "pi": pi_raw,
                   "dc_enh": dc_enh, "dc_enh_nb": dc_enh_nb, "dc_enh_wb": dc_enh_wb, "dc_enh_elo": dc_enh_elo,
                   "pre_market": pre_market, "post_market": post_market, "final": final},
        "negbin_applied": negbin_applied,
        "negbin_fusion_weight": NEGBIN_FUSION_WEIGHT if negbin_applied else 0,
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
        "weather": weather_data,
        "overdispersion": od_scoreline,
        "motivation": {
            "match_type": motivation_result.match_type.value if motivation_result else "not_computed",
            "matchday": motivation_result.matchday if motivation_result else None,
            "group_name": motivation_result.group_name if motivation_result else None,
            "home_motivation": motivation_result.home_motivation if motivation_result else 0.5,
            "away_motivation": motivation_result.away_motivation if motivation_result else 0.5,
            "ei_score": motivation_result.ei_score if motivation_result else 0.5,
            "home_win_adj": motivation_result.home_win_adj if motivation_result else 0.0,
            "draw_adj": motivation_result.draw_adj if motivation_result else 0.0,
            "away_win_adj": motivation_result.away_win_adj if motivation_result else 0.0,
            "collusion_risk": motivation_result.collusion_risk if motivation_result else 0.0,
            "rotation_risk_home": motivation_result.rotation_risk_home if motivation_result else 0.0,
            "rotation_risk_away": motivation_result.rotation_risk_away if motivation_result else 0.0,
            "explanation": motivation_result.explanation if motivation_result else "",
        },
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

    # ── 7.5. Persist prediction_runs to DB (V4.3.0 fix) ──
    # Previously only wrote JSON file + motivation_events, missing the
    # prediction_runs record that post-match eval and calibrator need.
    _prun_id = None
    try:
        import uuid as _uuid
        import sqlite3 as _sql3
        _db = str(BACKEND_DIR / "data" / "local_stage2.db")
        _conn = _sql3.connect(_db)
        _match_id = hashlib.md5(f"{HOME}|{AWAY}|{COMP}".encode()).hexdigest()[:32]
        _now = datetime.now(timezone.utc).isoformat()
        _prun_id = _uuid.uuid4().hex[:32]

        # Build Poisson score matrix (6x6, up to 5 goals each side)
        _hxg = dc_pred.get("home_xg", 0)
        _axg = dc_pred.get("away_xg", 0)
        _score_matrix = []
        for h in range(6):
            _row = []
            _ph = (_hxg ** h * math.exp(-_hxg) / math.factorial(h)) if _hxg > 0 else (1.0 if h == 0 else 0.0)
            for a in range(6):
                _pa = (_axg ** a * math.exp(-_axg) / math.factorial(a)) if _axg > 0 else (1.0 if a == 0 else 0.0)
                _row.append(_ph * _pa)
            _score_matrix.append(_row)

        # Build top3 scores from overdispersion top_15
        _top15 = od_scoreline.get("top_15_scorelines", [])[:3]
        _top3_json = json.dumps([{"score": s["score"], "prob": s["prob_pct"] / 100.0} for s in _top15])

        _conf_score = round(1.0 - abs(final["home_win_prob"] - 0.333) - abs(final["draw_prob"] - 0.333) - abs(final["away_win_prob"] - 0.333), 4)
        _conf_score = max(0.0, min(1.0, _conf_score))

        _feature_snap = json.dumps({
            "version": VERSION,
            "weight_label": wc.label,
            "pipeline": "dc->enhancer->negbin->weibull->elo->pi->market",
            "negbin_applied": negbin_applied,
            "negbin_weight": NEGBIN_FUSION_WEIGHT if negbin_applied else 0,
            "market_applied": market_live,
            "market_weight": market_weight,
            "market_provider": market_provider,
            "motivation_applied": motivation_result is not None and motivation_result.matchday == 3 if motivation_result else False,
            "calibration_applied": calibration_applied,
            "dc_enhancer_divergence": divergence,
            "competition": COMP,
            "is_neutral": IS_NEUTRAL,
            "wc_xg_calibration_factor": WC_XG_CALIBRATION_FACTOR,
            "negbin_r": NEGBIN_R,
        })

        _conn.execute("""
            INSERT OR REPLACE INTO prediction_runs
                (id, match_id, run_type, model_version, as_of_time,
                 home_win_prob, draw_prob, away_win_prob,
                 home_xg, away_xg, score_matrix, top3_scores,
                 confidence_score, risk_tags,
                 input_feature_snapshot, approved_signals, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            _prun_id, _match_id, "manual", VERSION, _now,
            round(final["home_win_prob"], 6), round(final["draw_prob"], 6), round(final["away_win_prob"], 6),
            round(_hxg, 4), round(_axg, 4),
            json.dumps(_score_matrix), _top3_json,
            _conf_score, "[]",
            _feature_snap, "[]", _now,
        ))
        _conn.commit()
        print(f"DB:       prediction_runs saved (id={_prun_id[:12]}...)")
    except Exception as _e:
        print(f"DB:       prediction_runs skipped ({_e})", file=sys.stderr)
    finally:
        try:
            _conn.close()
        except Exception:
            pass

    out = BACKEND_DIR / "data" / f"_pred_{HOME.replace(' ','_')}_{AWAY.replace(' ','_')}.json"
    with open(str(out), "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"Saved: {out.name}")


if __name__ == "__main__":
    main()

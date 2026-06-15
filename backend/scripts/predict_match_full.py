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

HOME = sys.argv[1] if len(sys.argv) > 1 else "Saudi Arabia"
AWAY = sys.argv[2] if len(sys.argv) > 2 else "Uruguay"
COMP = sys.argv[3] if len(sys.argv) > 3 else "FIFA World Cup 2026"
IS_NEUTRAL = True

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
    "provenance": {"dc_hash": hashlib.md5(dc_params_sorted).hexdigest()[:12],
                   "dc_teams": len(dc.attack_params), "training_rows": len(df),
                   "version": "3.8.0", "weight_label": wc.label},
}
out = BACKEND_DIR / "data" / f"_pred_{HOME.replace(' ','_')}_{AWAY.replace(' ','_')}.json"
with open(str(out), "w") as f:
    json.dump(result, f, indent=2, default=str)
print(f"Saved: {out.name}")

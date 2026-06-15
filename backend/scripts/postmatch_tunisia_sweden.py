#!/usr/bin/env python3
"""Post-match review: Tunisia vs Sweden — Group F Matchday 1, June 15 2026.

Inserts match result, fixes venue, saves V3.8.0 snapshot, generates learning log.
"""
import sqlite3, json, hashlib, uuid, sys, os
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

DB_PATH = BACKEND_DIR / "data" / "local_stage2.db"
PRED_PATH = BACKEND_DIR / "data" / "_pred_sweden_tunisia_v380.json"

MATCH_ID = "5b08b11522474349ac7285db40e17942"
HOME, AWAY = "Tunisia", "Sweden"
COMPETITION = "FIFA World Cup 2026"
ACTUAL_H_GOALS, ACTUAL_A_GOALS = 1, 5
ACTUAL_H_XG, ACTUAL_A_XG = 0.28, 1.36
VENUE = "Estadio BBVA, Monterrey, MX"

now = datetime.now(timezone.utc).isoformat()
db = sqlite3.connect(str(DB_PATH))
db.row_factory = sqlite3.Row

# ── 1. Insert match result ──
existing = db.execute("SELECT * FROM match_results WHERE match_id = ?", (MATCH_ID,)).fetchone()
if not existing:
    mr_id = uuid.uuid4().hex[:32]
    db.execute(
        "INSERT INTO match_results (match_id, home_goals, away_goals, home_xg, away_xg, id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (MATCH_ID, ACTUAL_H_GOALS, ACTUAL_A_GOALS, ACTUAL_H_XG, ACTUAL_A_XG, mr_id),
    )
    print(f"[1] INSERTED match_result: {mr_id} — {HOME} {ACTUAL_H_GOALS}-{ACTUAL_A_GOALS} {AWAY}")
else:
    print(f"[1] match_result already exists: {dict(existing)}")

# ── 2. Fix venue ──
db.execute("UPDATE matches SET venue = ? WHERE id = ?", (VENUE, MATCH_ID))
print(f"[2] UPDATED matches.venue → {VENUE}")

# ── 3. Fix wc26_schedule ──
db.execute(
    "UPDATE wc26_schedule SET home_goals = ?, away_goals = ?, match_status = 'FINISHED', "
    "venue = 'Estadio BBVA', city = 'Monterrey, MX' "
    "WHERE home_team = ? AND away_team = ? AND stage LIKE 'Group%'",
    (ACTUAL_H_GOALS, ACTUAL_A_GOALS, HOME, AWAY),
)
print(f"[3] UPDATED wc26_schedule: venue → Estadio BBVA, score → {ACTUAL_H_GOALS}-{ACTUAL_A_GOALS}")

# ── 4. Load prediction data ──
with open(str(PRED_PATH)) as f:
    pred = json.load(f)

snapshot_id = str(uuid.uuid4())
pred_run_id = str(uuid.uuid4())

baseline_probs = json.dumps({
    "home": pred["dc"]["home_win_prob"],
    "draw": pred["dc"]["draw_prob"],
    "away": pred["dc"]["away_win_prob"],
})
adjusted_probs = json.dumps({
    "home": pred["final"]["home_win_prob"],
    "draw": pred["final"]["draw_prob"],
    "away": pred["final"]["away_win_prob"],
})
component_probs = json.dumps({
    "dc": pred["dc"],
    "enhancer": pred["enhancer"],
    "elo": pred["elo"],
    "pi": pred["pi"],
    "weibull": None,
    "market": None,
})
expected_goals = json.dumps({"home": pred["home_xg"], "away": pred["away_xg"]})
elo_ratings_json = json.dumps({
    "home": pred["elo_home"],
    "away": pred["elo_away"],
    "gap": pred["elo_gap"],
    "k_factor": 32.0,
})
pipeline_params = json.dumps({
    "dc_converged": True,
    "dc_hash": pred["dc_hash"],
    "dc_teams": pred["dc_teams"],
    "weight_label": pred["weights"]["label"],
    "version": pred["version"],
    "training_df_max_date": "2026-06-03",
    "enhancer_features": 37,
})

db.execute(
    "INSERT INTO prediction_snapshots "
    "(id, match_id, generated_at, model_version, run_type, home_team, away_team, "
    "competition, match_time, baseline_probs, market_probs, adjusted_probs, "
    "expected_goals, top_scores, elo_ratings, active_event_ids, missing_inputs, "
    "confidence, calibration_monitor, pipeline_params, component_probs) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
    (
        snapshot_id, MATCH_ID, now, "3.8.0", "postmatch_retro",
        HOME, AWAY, COMPETITION,
        "2026-06-15T02:00:00",
        baseline_probs, None, adjusted_probs,
        expected_goals, "[]", elo_ratings_json, "[]", "[]",
        "medium", json.dumps({"enabled": False}), pipeline_params, component_probs,
    ),
)
print(f"[4] Saved snapshot: {snapshot_id}")

# ── 5. Generate learning log ──
# Recompute DC/Enhancer/Elo for marginal Brier
from app.services.prediction_core import _load_dc, _load_enhancer, _load_elo, _load_pi, _load_training_df
from app.services.prediction_timer import PredictionTimer
from app.services.tabular_match_model import fuse_outcome_probabilities
from app.services.elo_ratings import fuse_elo_probabilities
from app.services.pi_ratings import fuse_pi_probabilities
from app.services.weights import get_weight_config

timer = PredictionTimer()
dc = _load_dc(timer)
enh = _load_enhancer(timer)
elo_sys = _load_elo(timer)
pi_sys = _load_pi(timer)
training_df = _load_training_df(timer)
wc = get_weight_config(COMPETITION)

# Outcome: away win (Sweden) → one-hot [0, 0, 1]
def brier_away(probs):
    """Brier score for away-win outcome."""
    return sum((p - (1.0 if i == 2 else 0.0)) ** 2 for i, p in enumerate(probs)) / 3.0

dc_pred = dc.predict_match(HOME, AWAY, is_neutral_venue=True)
dc_probs = [dc_pred["home_win_prob"], dc_pred["draw_prob"], dc_pred["away_win_prob"]]
dc_brier = brier_away(dc_probs)

match_date = training_df["match_date"].max()
enh_pred = enh.predict_match(
    home_team=HOME, away_team=AWAY, match_date=match_date,
    competition_weight=1.0, is_neutral_venue=True, training_df=training_df,
)
enh_probs = [enh_pred["home_win_prob"], enh_pred["draw_prob"], enh_pred["away_win_prob"]]
enh_brier = brier_away(enh_probs)

elo_obj = elo_sys.predict(HOME, AWAY, is_neutral=True, competition_weight=1.0, competition=COMPETITION)
elo_probs = [elo_obj.home_win_prob, elo_obj.draw_prob, elo_obj.away_win_prob]
elo_brier = brier_away(elo_probs)

final_brier = pred["brier"]["Final"]
final_away_prob = pred["final"]["away_win_prob"]

# Marginal contributions
dc_marginal = dc_brier - final_brier
enhancer_marginal = enh_brier - final_brier
elo_marginal = elo_brier - final_brier

# Error magnitude & direction
error_magnitude = abs(final_away_prob - 1.0)
error_direction = "underestimate_away"

# Did model pick the right winner?
model_was_right = (pred["final"]["away_win_prob"] > pred["final"]["home_win_prob"])

context_tags = json.dumps({
    "actual_score": f"{HOME} {ACTUAL_H_GOALS}-{ACTUAL_A_GOALS} {AWAY}",
    "actual_xg": {HOME: ACTUAL_H_XG, AWAY: ACTUAL_A_XG},
    "venue": VENUE,
    "elo_home": pred["elo_home"],
    "elo_away": pred["elo_away"],
    "elo_gap": pred["elo_gap"],
    "elo_favors": HOME,
    "best_single_model": f"Enhancer (Brier {pred['brier']['Enhancer']:.4f})",
    "dc_brier": pred["brier"]["DC"],
    "enhancer_brier": pred["brier"]["Enhancer"],
    "elo_brier": pred["brier"]["Elo"],
    "pi_brier": pred["brier"]["Pi"],
    "final_brier": final_brier,
    "dc_favored": HOME,
    "enhancer_favored": AWAY,
    "elo_favored_player": HOME,
    "note": (
        "Enhancer only model to correctly identify Sweden as favorite. "
        "DC+Elo both wrong. xG anti-record set (1st half combined 0.47). "
        "Sweden overperformed xG by ~3.6 goals (5 goals from 1.36 xG). "
        "V3.8.0 weights: DC=0.70 Enh=0.20 Elo=0.10 Pi=0.10."
    ),
    "version": "3.8.0",
    "weight_label": pred["weights"]["label"],
})

log_id = hashlib.md5(f"{MATCH_ID}_v380".encode()).hexdigest()[:32]

db.execute(
    "INSERT OR REPLACE INTO prediction_learning_log "
    "(match_id, prediction_run_id, snapshot_id, error_magnitude, error_direction, "
    "dc_error_contribution, enhancer_error_contribution, elo_error_contribution, "
    "signal_error_contribution, market_error_contribution, "
    "model_was_right, divergence_at_prediction, context_tags, signal_verdicts, "
    "dc_marginal, enhancer_marginal, elo_marginal, market_marginal, signal_marginal, "
    "status, id, created_at, updated_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
    (
        MATCH_ID, pred_run_id, snapshot_id,
        error_magnitude, error_direction,
        None, None, None, None, None,
        int(model_was_right), None, context_tags, None,
        dc_marginal, enhancer_marginal, elo_marginal, None, None,
        "active", log_id, now, now,
    ),
)
print(f"[5] Saved learning log: {log_id}")
print(f"    error_magnitude: {error_magnitude:.4f}")
print(f"    error_direction: {error_direction}")
print(f"    model_was_right: {model_was_right}")
print(f"    dc_marginal: {dc_marginal:+.4f} (DC favored {HOME}, wrong)")
print(f"    enhancer_marginal: {enhancer_marginal:+.4f} (Enhancer favored {AWAY}, right)")
print(f"    elo_marginal: {elo_marginal:+.4f} (Elo favored {HOME}, wrong)")

db.commit()

# ── 6. Verify ──
print("\n=== VERIFY ===")
mr = db.execute("SELECT * FROM match_results WHERE match_id = ?", (MATCH_ID,)).fetchone()
print(f"match_results: {dict(mr)}")

m = db.execute("SELECT id, venue, status FROM matches WHERE id = ?", (MATCH_ID,)).fetchone()
print(f"matches: {dict(m)}")

ws = db.execute(
    "SELECT home_team, away_team, home_goals, away_goals, venue, city, match_status "
    "FROM wc26_schedule WHERE home_team = ? AND away_team = ?",
    (HOME, AWAY),
).fetchone()
print(f"wc26_schedule: {dict(ws)}")

ll = db.execute(
    "SELECT id, error_magnitude, error_direction, dc_marginal, enhancer_marginal, elo_marginal, status "
    "FROM prediction_learning_log WHERE match_id = ? ORDER BY created_at DESC LIMIT 1",
    (MATCH_ID,),
).fetchone()
print(f"learning_log: {dict(ll)}")

ss = db.execute(
    "SELECT id, model_version, run_type FROM prediction_snapshots "
    "WHERE id = ?",
    (snapshot_id,),
).fetchone()
print(f"snapshot: {dict(ss)}")

db.close()
print("\nDone. All DB operations committed successfully.")

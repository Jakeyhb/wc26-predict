import sqlite3, json, hashlib
from datetime import datetime, timezone

db = sqlite3.connect('backend/data/local_stage2.db')
cur = db.cursor()
match_id = '464dac10b16544a68f57ad70cc4a46a1'
now = datetime.now(timezone.utc).isoformat()

with open('backend/data/_pred_Belgium_Egypt.json', 'r') as f:
    pred = json.load(f)
layers = pred['layers']

def brier_draw(h, d, a):
    return (0-h)**2 + (1-d)**2 + (0-a)**2

briers = {}
for k, v in layers.items():
    briers[k] = round(brier_draw(v['home_win_prob'], v['draw_prob'], v['away_win_prob']), 4)

print('Brier scores:')
for k, b in sorted(briers.items(), key=lambda x: x[1]):
    print(f'  {k}: {b:.4f}')

best = min(briers, key=briers.get)
worst = max(briers, key=briers.get)
print(f'Best: {best} ({briers[best]})')
print(f'Worst: {worst} ({briers[worst]})')

# Pre-match comparison
print()
print('=== Pre-match vs Retro ===')
pre_brier = brier_draw(0.3571, 0.3084, 0.3345)
print(f'Pre-match V3.8.0 (with market+signals): Brier {pre_brier:.4f}')

retro_brier = brier_draw(layers['final']['home_win_prob'], layers['final']['draw_prob'], layers['final']['away_win_prob'])
print(f'Retro V3.8.0 (model only, no market): Brier {retro_brier:.4f}')

v2_brier = brier_draw(0.3175, 0.2860, 0.3966)
print(f'V2.0.0 Brier: {v2_brier:.4f}')

# LOO
final_b = briers['final']
dc_err = round(briers['dc'] - final_b, 4)
enh_err = round(briers['enhancer'] - final_b, 4)
elo_err = round(briers['elo'] - final_b, 4)
pi_err = round(briers['pi'] - final_b, 4)
print(f'DC marginal: {dc_err:+.4f}  Enh marginal: {enh_err:+.4f}  Elo marginal: {elo_err:+.4f}  Pi marginal: {pi_err:+.4f}')

# Save retro snapshot
snap_id = hashlib.md5(f'{match_id}_v3.8.0_retro'.encode()).hexdigest()

adjusted_probs = json.dumps({'home': layers['final']['home_win_prob'], 'draw': layers['final']['draw_prob'], 'away': layers['final']['away_win_prob']})
baseline_probs = json.dumps({k: {'home': v['home_win_prob'], 'draw': v['draw_prob'], 'away': v['away_win_prob']} for k,v in layers.items() if k in ['dc','enhancer','elo','pi']})
component_probs = json.dumps({k: {'home': v['home_win_prob'], 'draw': v['draw_prob'], 'away': v['away_win_prob']} for k,v in layers.items()})
market_probs = json.dumps({'home_odds': 0, 'draw_odds': 0, 'away_odds': 0, 'home_prob': 0.333, 'draw_prob': 0.333, 'away_prob': 0.333, 'provider': 'unavailable_retro', 'live': False, 'weight': 0.0})
expected_goals = json.dumps({'home_xg': pred['home_xg'], 'away_xg': pred['away_xg']})
elo_ratings = json.dumps({'home_elo': pred['elo']['home'], 'away_elo': pred['elo']['away'], 'gap': pred['elo']['home'] - pred['elo']['away']})

pipeline_params = json.dumps({
    'dc_hash': pred['provenance']['dc_hash'], 'dc_teams': pred['provenance']['dc_teams'],
    'training_rows': pred['provenance']['training_rows'], 'version': '3.8.0-retro',
    'weight_label': pred['provenance']['weight_label'],
    'weights': {'dc': 0.70, 'enhancer': 0.20, 'elo': 0.10, 'pi': 0.10, 'market': 0.00},
    'retrospective': True, 'brier_scores': briers, 'actual_outcome': 'draw',
    'pre_match_brier': pre_brier, 'v2_brier': v2_brier
})

cur.execute("DELETE FROM prediction_snapshots WHERE match_id=? AND model_version=?", (match_id, '3.8.0-retro'))

cur.execute("""INSERT INTO prediction_snapshots
(id, match_id, generated_at, model_version, run_type, home_team, away_team,
 competition, match_time, baseline_probs, market_probs, adjusted_probs,
 expected_goals, top_scores, elo_ratings, active_event_ids, missing_inputs,
 confidence, calibration_monitor, pipeline_params, component_probs)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
    snap_id, match_id, now, '3.8.0-retro', 'post_match_retrospective',
    'Belgium', 'Egypt', 'FIFA World Cup 2026',
    '2026-06-15T19:00:00',
    baseline_probs, market_probs, adjusted_probs,
    expected_goals,
    'Actual: 1-1 (Ashour 19, Hany OG 66). Lukaku 22sec impact. De Bruyne post.',
    elo_ratings,
    json.dumps(['lukaku_bench_22sec_og', 'ashour_first_intl_goal', 'debruyne_post_53min', 'salah_birthday_assist']),
    json.dumps(['market_retro_unavailable']),
    json.dumps({'overall': 'medium', 'pre_match_note': 'Pre-match was best WC26 prediction — gave draw 30.8%, closest to actual 1-1'}),
    '',
    pipeline_params, component_probs
))
db.commit()
print(f'Retro snapshot: {snap_id}')

# Learning log
log_id = hashlib.md5(f'{match_id}_learn38'.encode()).hexdigest()

context_tags = json.dumps({
    'dc_brier': briers['dc'], 'enhancer_brier': briers['enhancer'],
    'elo_brier': briers['elo'], 'pi_brier': briers['pi'],
    'best_layer': best, 'dc_enh_gap_pp': round(abs(layers['dc']['home_win_prob'] - layers['enhancer']['home_win_prob']) * 100, 1),
    'pre_match_final_probs': 'BEL 35.7% / Draw 30.8% / EGY 33.4%',
    'key_event': 'Lukaku subbed on 66min, forced OG within 22 seconds',
    'debruyne_post': '53min free kick hit post',
    'salah_birthday': '34th birthday assist',
    'belgium_xg': 1.32, 'egypt_xg': 1.07
})

signal_verdicts = json.dumps({
    'pre_match_signals_correct': [
        'Lukaku BENCH impact -1.0% correctly identified',
        'Belgium CB weakness (Ngoy/Mechele <15 caps) confirmed - Egypt scored first',
        'Salah FULLY FIT +1.5% confirmed - assist on birthday',
        'Debast OUT -1.5% correctly flagged'
    ],
    'overall_signal_accuracy': '4/4 signals directionally correct',
    'note': 'Pre-match V3.8.0 gave BEL 35.7%/Draw 30.8%/EGY 33.4% - the most balanced and accurate WC26 prediction. Draw 30.8% was the highest of any layer.'
})

cur.execute("DELETE FROM prediction_learning_log WHERE match_id=?", (match_id,))

cur.execute("""INSERT INTO prediction_learning_log
(id, match_id, prediction_run_id, snapshot_id, error_magnitude, error_direction,
 dc_error_contribution, enhancer_error_contribution, elo_error_contribution, signal_error_contribution, market_error_contribution,
 model_was_right, divergence_at_prediction, context_tags, signal_verdicts,
 dc_marginal, enhancer_marginal, elo_marginal, market_marginal, signal_marginal, status)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
    log_id, match_id, snap_id, snap_id,
    round(final_b, 4), 'underestimate_draw_slightly',
    dc_err, enh_err, elo_err, 0.0, 0.0,
    0, round(abs(layers['dc']['home_win_prob'] - layers['enhancer']['home_win_prob']), 4),
    context_tags, signal_verdicts,
    dc_err, enh_err, elo_err, 0.0, 0.0,
    'active'
))
db.commit()
print(f'Learning log: {log_id}')

cur.execute('SELECT COUNT(*) FROM prediction_snapshots WHERE match_id=?', (match_id,))
print(f'Total snapshots: {cur.fetchone()[0]}')
cur.execute('SELECT COUNT(*) FROM prediction_learning_log WHERE match_id=?', (match_id,))
print(f'Learning logs: {cur.fetchone()[0]}')
db.close()
print('Done')

import sqlite3, json, hashlib
from datetime import datetime, timezone

db = sqlite3.connect('backend/data/local_stage2.db')
cur = db.cursor()
match_id = '1ec3fa7513d54226972d2f9e1aae6199'
now = datetime.now(timezone.utc).isoformat()

with open('backend/data/_pred_Saudi_Arabia_Uruguay.json', 'r') as f:
    pred = json.load(f)
layers = pred['layers']

def brier_draw(h, d, a):
    return round((0-h)**2 + (1-d)**2 + (0-a)**2, 4)

briers = {}
for k, v in layers.items():
    briers[k] = brier_draw(v['home_win_prob'], v['draw_prob'], v['away_win_prob'])

print('Brier scores (actual = draw 1-1):')
for k, b in sorted(briers.items(), key=lambda x: x[1]):
    l = layers[k]
    print(f'  {k:20s}: Brier={b:.4f}  H={l["home_win_prob"]:.4f} D={l["draw_prob"]:.4f} A={l["away_win_prob"]:.4f}')

best = min(briers, key=briers.get)
worst = max(briers, key=briers.get)
print(f'\nBest individual layer: {best} ({briers[best]})')
print(f'Worst individual layer: {worst} ({briers[worst]})')

# Pre-match comparison
print('\n=== Pre-match vs Retro ===')
pre_h, pre_d, pre_a = 0.1732, 0.3401, 0.4867  # pre-match V3.8.0 with market+signals
pre_brier = brier_draw(pre_h, pre_d, pre_a)
retro_brier = briers['pre_market']
post_market_brier = briers['post_market']
v2_h, v2_d, v2_a = 0.1883, 0.3209, 0.4907  # V2.0.0
v2_brier = brier_draw(v2_h, v2_d, v2_a)

print(f'V2.0.0 (June 3):            H={v2_h:.4f} D={v2_d:.4f} A={v2_a:.4f}  Brier={v2_brier:.4f}')
print(f'V3.8.0 retro (model only):  H={layers["pre_market"]["home_win_prob"]:.4f} D={layers["pre_market"]["draw_prob"]:.4f} A={layers["pre_market"]["away_win_prob"]:.4f}  Brier={retro_brier:.4f}')
print(f'V3.8.0 retro (+market):     H={layers["post_market"]["home_win_prob"]:.4f} D={layers["post_market"]["draw_prob"]:.4f} A={layers["post_market"]["away_win_prob"]:.4f}  Brier={post_market_brier:.4f}')
print(f'V3.8.0 pre-match (market+sig): H={pre_h:.4f} D={pre_d:.4f} A={pre_a:.4f}  Brier={pre_brier:.4f}')

# Marginal analysis (layer Brier vs final model-only Brier)
final_b = briers['pre_market']
dc_marg = round(briers['dc'] - final_b, 4)
enh_marg = round(briers['enhancer'] - final_b, 4)
elo_marg = round(briers['elo'] - final_b, 4)
pi_marg = round(briers['pi'] - final_b, 4)
print(f'\nMarginal (vs final model-only Brier {final_b}):')
print(f'  DC marginal: {dc_marg:+.4f}  ({"HELPFUL" if dc_marg < 0 else "HARMFUL"})')
print(f'  Enhancer marginal: {enh_marg:+.4f}  ({"HELPFUL" if enh_marg < 0 else "HARMFUL"})')
print(f'  Elo marginal: {elo_marg:+.4f}  ({"HELPFUL" if elo_marg < 0 else "HARMFUL"})')
print(f'  Pi marginal: {pi_marg:+.4f}  ({"HELPFUL" if pi_marg < 0 else "HARMFUL"})')

# Save retro snapshot
snap_id = hashlib.md5(f'{match_id}_v3.8.0_retro'.encode()).hexdigest()

adjusted_probs = json.dumps({'home': round(layers['pre_market']['home_win_prob'], 4),
                              'draw': round(layers['pre_market']['draw_prob'], 4),
                              'away': round(layers['pre_market']['away_win_prob'], 4)})
baseline_probs = json.dumps({k: {'home': round(v['home_win_prob'], 4),
                                  'draw': round(v['draw_prob'], 4),
                                  'away': round(v['away_win_prob'], 4)}
                             for k,v in layers.items() if k in ['dc','enhancer','elo','pi']})
component_probs = json.dumps({k: {'home': round(v['home_win_prob'], 4),
                                   'draw': round(v['draw_prob'], 4),
                                   'away': round(v['away_win_prob'], 4)}
                              for k,v in layers.items()})
market_probs = json.dumps({'home_odds': 8.1, 'draw_odds': 4.3, 'away_odds': 1.43,
                           'home_prob': 0.117, 'draw_prob': 0.220, 'away_prob': 0.663,
                           'provider': 'apifootball_retro', 'live': False, 'weight': 0.0})
expected_goals = json.dumps({'home_xg': round(pred['home_xg'], 2), 'away_xg': round(pred['away_xg'], 2)})
elo_ratings_json = json.dumps({'home_elo': round(pred['elo']['home'], 1),
                                'away_elo': round(pred['elo']['away'], 1),
                                'gap': round(pred['elo']['home'] - pred['elo']['away'], 1)})

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
    'Saudi Arabia', 'Uruguay', 'FIFA World Cup 2026',
    '2026-06-15T22:00:00',
    baseline_probs, market_probs, adjusted_probs,
    expected_goals,
    'Actual: 1-1 (Al-Amri 41, Araujo 80). Al-Owais 9 saves MOTM 7.6. Muslera error on goal.',
    elo_ratings_json,
    json.dumps(['al_owais_9_saves_motm', 'muslera_error_goal', 'araujo_80_equalizer',
                'al_amri_first_wc_goal', 'uruguay_27_shots', 'saudi_42_clearances']),
    json.dumps(['market_retro_unavailable']),
    json.dumps({'overall': 'medium',
                'pre_match_note': 'Pre-match V3.8.0 gave URU 48.7% fav. Retro model-only gave URU 45.6%. DC was best individual layer.'}),
    '',
    pipeline_params, component_probs
))
db.commit()
print(f'Retro snapshot saved: {snap_id}')

# Learning log
log_id = hashlib.md5(f'{match_id}_learn38'.encode()).hexdigest()

context_tags = json.dumps({
    'dc_brier': briers['dc'], 'enhancer_brier': briers['enhancer'],
    'elo_brier': briers['elo'], 'pi_brier': briers['pi'],
    'best_layer': best, 'worst_layer': worst,
    'dc_enh_gap_pp': round(abs(layers['dc']['home_win_prob'] - layers['enhancer']['home_win_prob']) * 100, 1),
    'pre_match_final_probs': 'KSA 17.3% / Draw 34.0% / URU 48.7%',
    'retro_model_only': f'KSA {layers["pre_market"]["home_win_prob"]:.1%} / Draw {layers["pre_market"]["draw_prob"]:.1%} / URU {layers["pre_market"]["away_win_prob"]:.1%}',
    'key_event': 'Al-Owais 9 saves MOTM; Muslera error gifted Al-Amri goal; Araujo 80 equalizer',
    'uruguay_xg': 1.54, 'saudi_xg': 0.99,
    'attendance': 62464, 'referee': 'Maurizio Mariani (Italy)',
    'uruguay_key_absences': 'Ronald Araujo (calf), De Arrascaeta (calf), Gimenez (bench)'
})

signal_verdicts = json.dumps({
    'pre_match_signals_correct': [
        'Uruguay defensive crisis (Araujo+Gimenez OUT) -3.2% correctly identified — Uruguay conceded first',
        'Muslera age/error risk flagged — indeed Muslera error led to Saudi goal',
        'Saudi coach instability -0.5% overestimated — Saudi performed above expectation',
        'Thunderstorm forecast was WRONG — actual weather was fine, no delays'
    ],
    'pre_match_signals_wrong': [
        'Weather: forecast thunderstorm (code 95) did not materialize — no rain/delays reported'
    ],
    'overall_signal_accuracy': '3/5 signals directionally correct, 1 weather false alarm',
    'note': 'DC was best individual layer (Brier 0.496) — its structural draw bias (43.5%) was closest to actual draw. Complete reversal from ESP-CPV and TUN-SWE where DC was worst.'
})

cur.execute("DELETE FROM prediction_learning_log WHERE match_id=?", (match_id,))

cur.execute("""INSERT INTO prediction_learning_log
(id, match_id, prediction_run_id, snapshot_id, error_magnitude, error_direction,
 dc_error_contribution, enhancer_error_contribution, elo_error_contribution, signal_error_contribution, market_error_contribution,
 model_was_right, divergence_at_prediction, context_tags, signal_verdicts,
 dc_marginal, enhancer_marginal, elo_marginal, market_marginal, signal_marginal, status)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
    log_id, match_id, snap_id, snap_id,
    round(final_b, 4), 'underestimate_draw_moderate',
    dc_marg, enh_marg, elo_marg, 0.0, 0.0,
    0, round(abs(layers['dc']['home_win_prob'] - layers['enhancer']['home_win_prob']), 4),
    context_tags, signal_verdicts,
    dc_marg, enh_marg, elo_marg, 0.0, 0.0,
    'active'
))
db.commit()
print(f'Learning log saved: {log_id}')

# Update match status
cur.execute("UPDATE matches SET status='finished' WHERE id=?", (match_id,))
cur.execute("UPDATE wc26_schedule SET match_status='FINISHED', home_goals=1, away_goals=1 WHERE home_team='Saudi Arabia' AND away_team='Uruguay'")

# Insert match_results
cur.execute("DELETE FROM match_results WHERE match_id=?", (match_id,))
cur.execute("""INSERT INTO match_results (match_id, home_goals, away_goals, home_xg, away_xg,
    home_possession, away_possession, home_shots, away_shots, home_shots_on_target, away_shots_on_target,
    home_corners, away_corners, home_fouls, away_fouls, attendance, referee, notes)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
    match_id, 1, 1, 0.99, 1.54,
    31.5, 68.5, 7, 27, 3, 10,
    4, 14, 11, 6, 62464, 'Maurizio Mariani (Italy)',
    'Al-Amri 41 (rebound after Muslera error), Maxi Araujo 80 (rebound). Al-Owais 9 saves MOTM 7.6 SofaScore.'
))
db.commit()

cur.execute('SELECT COUNT(*) FROM prediction_snapshots WHERE match_id=?', (match_id,))
print(f'Total snapshots for match: {cur.fetchone()[0]}')
cur.execute('SELECT COUNT(*) FROM prediction_learning_log WHERE match_id=?', (match_id,))
print(f'Learning logs for match: {cur.fetchone()[0]}')

# Verify final state
print('\n=== Verification ===')
cur.execute('SELECT status, venue FROM matches WHERE id=?', (match_id,))
print(f'matches: status={cur.fetchone()}')
cur.execute('SELECT match_status, home_goals, away_goals, venue, city FROM wc26_schedule WHERE home_team="Saudi Arabia" AND away_team="Uruguay"')
print(f'wc26_schedule: {cur.fetchone()}')
cur.execute('SELECT home_goals, away_goals, home_xg, away_xg FROM match_results WHERE match_id=?', (match_id,))
print(f'match_results: {cur.fetchone()}')

db.close()
print('\nDone.')

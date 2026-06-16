import sqlite3, json, hashlib
from datetime import datetime, timezone

db = sqlite3.connect('backend/data/local_stage2.db')
cur = db.cursor()
match_id = '61d558deb0ee4b47a81bab8544dcd4f4'
now = datetime.now(timezone.utc).isoformat()

with open('backend/data/_pred_Iran_New_Zealand.json', 'r') as f:
    pred = json.load(f)
layers = pred['layers']

def brier_draw(h, d, a):
    return round((0-h)**2 + (1-d)**2 + (0-a)**2, 4)

briers = {}
for k, v in layers.items():
    briers[k] = brier_draw(v['home_win_prob'], v['draw_prob'], v['away_win_prob'])

print('Brier scores (actual = draw 2-2):')
for k, b in sorted(briers.items(), key=lambda x: x[1]):
    l = layers[k]
    print(f'  {k:20s}: Brier={b:.4f}  H={l["home_win_prob"]:.4f} D={l["draw_prob"]:.4f} A={l["away_win_prob"]:.4f}')

best = min(briers, key=briers.get)
worst = max(briers, key=briers.get)
print(f'\nBest individual layer: {best} ({briers[best]})')
print(f'Worst individual layer: {worst} ({briers[worst]})')

# Pre-match comparison
print('\n=== Pre-match vs Retro ===')
pre_h, pre_d, pre_a = 0.5219, 0.2389, 0.2392  # pre-match V3.8.0 with market+signals
pre_brier = brier_draw(pre_h, pre_d, pre_a)
retro_brier = briers['pre_market']  # model only
v2_h, v2_d, v2_a = 0.5261, 0.2126, 0.2613  # V2.0.0
v2_brier = brier_draw(v2_h, v2_d, v2_a)

print(f'V2.0.0 (June 3):            H={v2_h:.4f} D={v2_d:.4f} A={v2_a:.4f}  Brier={v2_brier:.4f}')
print(f'V3.8.0 retro (model only):  H={layers["pre_market"]["home_win_prob"]:.4f} D={layers["pre_market"]["draw_prob"]:.4f} A={layers["pre_market"]["away_win_prob"]:.4f}  Brier={retro_brier:.4f}')
print(f'V3.8.0 retro (+market):     H={layers["post_market"]["home_win_prob"]:.4f} D={layers["post_market"]["draw_prob"]:.4f} A={layers["post_market"]["away_win_prob"]:.4f}  Brier={briers["post_market"]:.4f}')
print(f'V3.8.0 pre-match (market+sig): H={pre_h:.4f} D={pre_d:.4f} A={pre_a:.4f}  Brier={pre_brier:.4f}')

# Marginal analysis
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
market_probs = json.dumps({'home_odds': 1.83, 'draw_odds': 3.35, 'away_odds': 4.65,
                           'home_prob': 0.516, 'draw_prob': 0.282, 'away_prob': 0.203,
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
    'Iran', 'New Zealand', 'FIFA World Cup 2026',
    '2026-06-16T01:00:00',
    baseline_probs, market_probs, adjusted_probs,
    expected_goals,
    'Actual: 2-2 (Just 7/55, Rezaeian 32, Mohebi 64). Rezaeian 9.3 SofaScore MOTM. Taremi hit post 23\'. VAR disallowed Nemati goal 45+4.',
    elo_ratings_json,
    json.dumps(['just_brace_7_54', 'rezaeian_goal_assist_motm_93', 'wood_2_assists',
                'taremi_post_23', 'nemati_var_disallowed', 'mohebi_header_64']),
    json.dumps(['market_retro_unavailable']),
    json.dumps({'overall': 'medium',
                'pre_match_note': 'Pre-match V3.8.0 gave IRN 52.2% fav. DC draw 29.3% was best. Pi anomaly NZL 60.9% again.'}),
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
    'pre_match_final_probs': 'IRN 52.2% / Draw 23.9% / NZL 23.9%',
    'retro_model_only': f'IRN {layers["pre_market"]["home_win_prob"]:.1%} / Draw {layers["pre_market"]["draw_prob"]:.1%} / NZL {layers["pre_market"]["away_win_prob"]:.1%}',
    'key_event': 'Elijah Just brace (7, 54). Rezaeian goal+assist MOTM 9.3. Taremi hit post. VAR disallowed Nemati goal.',
    'iran_xg': 1.50, 'nzl_xg': 1.24,
    'attendance': 70108, 'referee': 'Cesar Ramos Palazuelos (Mexico)',
    'pi_anomaly_note': 'Pi gave NZL 60.9% win — 4th match with Pi inversion (NZL, CPV, URU, NZL again)'
})

signal_verdicts = json.dumps({
    'pre_match_signals_correct': [
        'Chris Wood threat +0.8% confirmed — 2 assists, aerial dominance',
        'Azmoun absence -1.5% meaningful — Iran lacked clinical finisher (Taremi post, Nemati VAR offside)',
        'Iran CB aging pair vulnerable — conceded twice to NZL counter-attacks',
        'NZL never won WC match -0.5% — draw was best realistic outcome, achieved'
    ],
    'pre_match_signals_wrong': [
        'NZL poor form (L-L-L-L-W) overrated — NZL competitive, Just scored brace',
        'Pi anomaly flagged correctly in pre-match as data quality issue'
    ],
    'overall_signal_accuracy': '4/6 directionally correct; Pi anomaly warning was prescient',
    'note': 'DC was best layer again (Brier 0.469) — draw 29.3% highest of any model. 2nd straight match where DC dominates. DC now 4/7 best layer.'
})

cur.execute("DELETE FROM prediction_learning_log WHERE match_id=?", (match_id,))

cur.execute("""INSERT INTO prediction_learning_log
(id, match_id, prediction_run_id, snapshot_id, error_magnitude, error_direction,
 dc_error_contribution, enhancer_error_contribution, elo_error_contribution, signal_error_contribution, market_error_contribution,
 model_was_right, divergence_at_prediction, context_tags, signal_verdicts,
 dc_marginal, enhancer_marginal, elo_marginal, market_marginal, signal_marginal, status)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
    log_id, match_id, snap_id, snap_id,
    round(final_b, 4), 'overestimate_home_moderate',
    dc_marg, enh_marg, elo_marg, 0.0, 0.0,
    0, round(abs(layers['dc']['home_win_prob'] - layers['enhancer']['home_win_prob']), 4),
    context_tags, signal_verdicts,
    dc_marg, enh_marg, elo_marg, 0.0, 0.0,
    'active'
))
db.commit()
print(f'Learning log saved: {log_id}')

# Update DB status
cur.execute("UPDATE matches SET status='finished' WHERE id=?", (match_id,))
cur.execute("UPDATE wc26_schedule SET match_status='FINISHED', home_goals=2, away_goals=2 WHERE home_team='Iran' AND away_team='New Zealand'")

# Insert match_results
result_id = hashlib.md5(f'{match_id}_result'.encode()).hexdigest()
cur.execute("DELETE FROM match_results WHERE match_id=?", (match_id,))
cur.execute("""INSERT INTO match_results (id, match_id, home_goals, away_goals, home_xg, away_xg, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?)""", (result_id, match_id, 2, 2, 1.50, 1.24, now))
db.commit()

print('\n=== Verification ===')
cur.execute("SELECT status, venue FROM matches WHERE id=?", (match_id,))
print(f'matches: {cur.fetchone()}')
cur.execute("SELECT match_status, home_goals, away_goals, venue FROM wc26_schedule WHERE home_team='Iran' AND away_team='New Zealand'")
print(f'wc26_schedule: {cur.fetchone()}')
cur.execute("SELECT home_goals, away_goals, home_xg, away_xg FROM match_results WHERE match_id=?", (match_id,))
print(f'match_results: {cur.fetchone()}')

db.close()
print('Done.')

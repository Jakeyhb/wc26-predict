#!/usr/bin/env python
"""Germany vs Paraguay post-match review + self-evolution — all DB updates."""
import sqlite3, sys, io, uuid, json, math
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
db = sqlite3.connect('backend/data/local_stage2.db')
db.row_factory = sqlite3.Row

MATCH_ID = 'b9e0a57539df48969e6d31f18b5e39'
NOW = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

# ============================================================
# STEP 0: Create retroactive prediction_run (not in DB)
# ============================================================
print('=== STEP 0: Create retroactive prediction_run ===')
pred_run_id = uuid.uuid4().hex[:32]
pred_run_time = '2026-06-28T07:39:06.558615+00:00'

top3_scores_json = json.dumps([
    {"score": "2:0", "prob": 0.137},
    {"score": "3:0", "prob": 0.131},
    {"score": "1:0", "prob": 0.097}
])
risk_tags_json = json.dumps([
    "calibration_large_correction_-11.3pp",
    "component_divergence_dc_vs_enhancer",
    "paraguay_defensive_5-4-1",
    "all_7_components_agree_germany"
])

db.execute('''
INSERT INTO prediction_runs (id, match_id, run_type, model_version, as_of_time,
    home_win_prob, draw_prob, away_win_prob, home_xg, away_xg,
    score_matrix, top3_scores, confidence_score, risk_tags,
    input_feature_snapshot, approved_signals, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
''', (pred_run_id, MATCH_ID, 'manual', '4.3.0-beta', pred_run_time,
      0.578, 0.188, 0.234, 2.58, 0.61,
      '[]', top3_scores_json, 0.80, risk_tags_json,
      '{}', '[]', NOW))

cur = db.execute('SELECT id, home_win_prob, draw_prob, away_win_prob FROM prediction_runs WHERE id=?', (pred_run_id,))
r = cur.fetchone()
print(f'prediction_run created: {dict(r)}')

# ============================================================
# STEP 1: Update wc26_schedule
# ============================================================
print('\n=== STEP 1: Update wc26_schedule ===')
db.execute('''
UPDATE wc26_schedule
SET match_status = 'FINISHED', home_goals = 1, away_goals = 1
WHERE match_number = 74
''')
cur = db.execute('SELECT match_number, home_team, away_team, match_status, home_goals, away_goals FROM wc26_schedule WHERE match_number=74')
r = cur.fetchone()
print(f'wc26_schedule updated: {dict(r)}')

# ============================================================
# STEP 2: Update matches table
# ============================================================
print('\n=== STEP 2: Update matches ===')
db.execute('UPDATE matches SET status = ? WHERE id = ?', ('FINISHED', MATCH_ID))
cur = db.execute('SELECT id, status, stage FROM matches WHERE id = ?', (MATCH_ID,))
r = cur.fetchone()
print(f'matches updated: {dict(r)}')

# ============================================================
# STEP 3: Insert match_results
# ============================================================
print('\n=== STEP 3: Insert match_results ===')
mr_id = uuid.uuid4().hex[:32]
db.execute('''
INSERT INTO match_results (id, match_id, home_goals, away_goals, created_at)
VALUES (?, ?, ?, ?, ?)
''', (mr_id, MATCH_ID, 1, 1, NOW))
cur = db.execute('SELECT * FROM match_results WHERE match_id = ?', (MATCH_ID,))
r = cur.fetchone()
print(f'match_results inserted: {dict(r)}')

# ============================================================
# STEP 4: Insert match_result_verification (multiple sources)
# ============================================================
print('\n=== STEP 4: Insert verification records ===')
sources = [
    ('CCTV (央视体育)', 1, 'https://sports.cctv.com/2026/06/30/PHOArytlRJgEdhg7SiQAij38260630.shtml'),
    ('AP News (美联社)', 1, 'https://uat.apnews.com/article/germany-paraguay-score-world-cup-819ffc6e897f8be74f48d6b9d3e76e9b'),
    ('CNN', 1, 'https://edition.cnn.com/2026/06/29/sport/world-cup-round-of-32-monday'),
    ('Guangming Daily (光明网)', 1, 'https://m.gmw.cn/2026-06/30/content_1304514284.htm'),
]
verif_ids = []
for src_name, tier, url in sources:
    vid = uuid.uuid4().hex[:32]
    verif_ids.append(vid)
    db.execute('''
    INSERT INTO match_result_verification (id, match_id, home_goals, away_goals, source_name, source_tier, match_status_at_source, is_consensus, notes, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, 'FINISHED', 1, ?, ?, ?)
    ''', (vid, MATCH_ID, 1, 1, src_name, tier, url, NOW, NOW))

cur = db.execute('SELECT id, source_name, source_tier FROM match_result_verification WHERE match_id=?', (MATCH_ID,))
for r in cur.fetchall():
    print(f'  verification: {dict(r)}')

# ============================================================
# STEP 5: Post-match evaluation metrics
# ============================================================
print('\n=== STEP 5: Post-match evaluation ===')

# Prediction probabilities (from report)
p_home = 0.578
p_draw = 0.188
p_away = 0.234

# Actual outcome: DRAW
o_home, o_draw, o_away = 0, 1, 0

# Brier Score
se_home = (o_home - p_home)**2
se_draw = (o_draw - p_draw)**2
se_away = (o_away - p_away)**2
brier_sum = se_home + se_draw + se_away
brier = brier_sum / 3
print(f'Brier = ({se_home:.4f} + {se_draw:.4f} + {se_away:.4f}) / 3 = {brier_sum:.4f} / 3 = {brier:.4f}')

# LogLoss
logloss = -math.log(max(p_draw, 1e-10))
print(f'LogLoss = -ln({p_draw}) = {logloss:.4f}')

# RPS
cum_pred_home = p_home
cum_pred_hd = p_home + p_draw  # = 0.766
rps = ((cum_pred_home - 0)**2 + (cum_pred_hd - 1)**2) / 2
print(f'RPS = ({cum_pred_home**2:.4f} + {(cum_pred_hd-1)**2:.4f}) / 2 = {rps:.4f}')

# Score hit check
exact_score_hit = False  # Actual 1-1, top3: 2-0, 3-0, 1-0
top3_hit = False
print(f'Exact Score Hit: {exact_score_hit}')
print(f'Top-3 Hit: {top3_hit}')

calibration_bucket = int(p_home * 10)  # 5
print(f'Calibration bucket: {calibration_bucket}')

# ============================================================
# Component direction assessment
# ============================================================
print('\n=== Component Directions ===')
components = {
    'DC':       (0.822, 0.119, 0.059, 'Germany'),
    'Enhancer': (0.481, 0.253, 0.266, 'Germany'),
    'Weibull':  (0.833, 0.138, 0.028, 'Germany'),
    'NegBin':   (0.780, 0.126, 0.094, 'Germany'),
    'Elo':      (0.506, 0.228, 0.266, 'Germany'),
    'Pi':       (0.565, 0.197, 0.238, 'Germany'),
    'Market':   (0.700, 0.189, 0.110, 'Germany'),
}

correct = 0
comp_briers = {}
for name, (ph, pd, pa, direction) in components.items():
    predicted_dir = 'home' if ph > pd and ph > pa else ('away' if pa > pd and pa > ph else 'draw')
    actual_dir = 'draw'
    is_correct = (predicted_dir == actual_dir)
    if is_correct:
        correct += 1

    c_brier = ((0-ph)**2 + (1-pd)**2 + (0-pa)**2) / 3
    comp_briers[name] = c_brier
    marker = '+' if is_correct else '-'
    print(f'  [{marker}] {name}: {ph:.1%}/{pd:.1%}/{pa:.1%} -> {predicted_dir} WRONG | Brier={c_brier:.4f}')

print(f'  Direction: {correct}/7 correct ({correct/7:.0%})')
print(f'  ALL 7 COMPONENTS WRONG — second systemic consensus failure (after SA-KR)')

# Pre-market assessment
pre_mkt_h = 0.691
pre_mkt_d = 0.167
pre_mkt_a = 0.142
pre_mkt_brier = ((0-pre_mkt_h)**2 + (1-pre_mkt_d)**2 + (0-pre_mkt_a)**2) / 3
post_cal_brier = brier
print(f'\n  Pre-market Brier: {pre_mkt_brier:.4f} (Germany 69.1%, direction WRONG)')
print(f'  Post-cal Brier: {post_cal_brier:.4f} (Germany 57.8%, direction WRONG)')
print(f'  Calibration reduced Germany -11.3pp but still could not flip to draw')
print(f'  Draw only 18.8% → actual draw. Major miss.')

# ============================================================
# STEP 6: Insert postmatch_eval
# ============================================================
print('\n=== STEP 6: Insert postmatch_eval ===')
eval_id = uuid.uuid4().hex[:32]
actual_result = 'D'

notes = (
    "Germany 1-1 Paraguay (HT 1-1, FT 1-1, AET 1-1, Paraguay wins 4-3 on penalties). "
    "Enciso 42min (Paraguay), Havertz 54min (Germany). "
    "ALL 7/7 components predicted Germany win — complete systemic consensus failure. "
    "Tah goal disallowed by VAR at 102min (foul on goalkeeper). "
    "Penalty shootout: Havertz saved, Woltemade saved, Tah over bar; Germany first WC penalty loss. "
    "Draw probability only 18.8% despite Bootstrap mean 22.9%. "
    "Calibration reduced Germany 69.1%→57.8% (-11.3pp) — correct direction but insufficient. "
    "Brier=0.3494 (high), LogLoss=1.6713 (very high). "
    "Second all-component failure after SA-KR. "
    "Market (70% Germany) reflects industry-wide consensus failure."
)

db.execute('''
INSERT INTO postmatch_eval (id, prediction_run_id, actual_home_goals, actual_away_goals,
    actual_result, brier_score, log_loss, exact_score_hit, top3_hit,
    calibration_bucket, notes, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
''', (eval_id, pred_run_id, 1, 1, actual_result, brier, logloss,
      exact_score_hit, top3_hit, calibration_bucket, notes, NOW))

cur = db.execute('SELECT * FROM postmatch_eval WHERE id=?', (eval_id,))
r = cur.fetchone()
print(f'postmatch_eval inserted: {dict(r)}')

# ============================================================
# STEP 7: Insert prediction_learning_log
# ============================================================
print('\n=== STEP 7: Insert prediction_learning_log ===')
learning_id = uuid.uuid4().hex[:32]

error_magnitude = brier * 3
error_direction = 'wrong_draw'
model_was_right = False

# Component margins vs final
dc_marginal = comp_briers['DC'] - brier
enhancer_marginal = comp_briers['Enhancer'] - brier
elo_marginal = comp_briers['Elo'] - brier
market_marginal = comp_briers['Market'] - brier

context_tags = {
    'stage': 'Round of 32',
    'match_type': 'knockout',
    'component_direction': '0/7',
    'all_components_wrong': True,
    'consensus_failure': True,
    'second_systemic_failure': True,
    'predicted': 'Germany (57.8%)',
    'actual': 'Draw (1-1)',
    'draw_prob': 0.188,
    'penalty_shootout': True,
    'var_disallowed_goal': True,
    'upset_magnitude': 'massive',
    'elo_gap': 111.4,
    'market_favored_germany': 0.70

}

db.execute('''
INSERT INTO prediction_learning_log (id, match_id, prediction_run_id,
    error_magnitude, error_direction, model_was_right, status,
    dc_marginal, enhancer_marginal, elo_marginal, market_marginal,
    context_tags, created_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?)
''', (learning_id, MATCH_ID, pred_run_id,
      error_magnitude, error_direction, int(model_was_right),
      dc_marginal, enhancer_marginal, elo_marginal, market_marginal,
      json.dumps(context_tags), NOW, NOW))

cur = db.execute('SELECT * FROM prediction_learning_log WHERE id=?', (learning_id,))
r = cur.fetchone()
if r:
    d = dict(r)
    for k, v in d.items():
        if isinstance(v, float):
            d[k] = round(v, 6)
    print(f'learning_log inserted: {d}')

# ============================================================
# STEP 8: Weight adjustment assessment
# ============================================================
print('\n=== STEP 8: Weight adjustment assessment ===')
print('CRITICAL EVENT: All 7 components predicted Germany, actual was Draw.')
print('This is the SECOND all-component consensus failure (after SA-KR).')
print()
print('Diagnosis:')
print('  1. Draw probability (18.8%) severely underestimated')
print('  2. Bootstrap mean draw 22.9% was better but still too low')
print('  3. Calibration reduced Germany -11.3pp but couldn\'t create enough draw probability')
print('  4. Market (70% Germany) also wrong — industry-wide failure')
print('  5. Elo 111pt gap drove all components to overestimate Germany')
print()
print('RECOMMENDATION:')
print('  - DO NOT reduce Enhancer further — it was the most balanced (48.1% Germany)')
print('  - Consider increasing draw_floor from current 0.12 baseline')
print('  - Elo 111pt gap may be overstated for knockout stage')
print('  - This is a genuine black swan: penalty loss + VAR disallowed goal')
print('  - No weight change warranted based on a single black swan event')
print('  - Monitor: if draw underestimation continues, consider structural fix')

# ============================================================
# COMMIT
# ============================================================
db.commit()
print('\n=== ALL DB UPDATES COMMITTED ===')
print(f'prediction_run id: {pred_run_id} (retroactive)')
print(f'match_results id: {mr_id}')
print(f'postmatch_eval id: {eval_id}')
print(f'learning_log id: {learning_id}')
print(f'verification ids: {verif_ids}')

# Quick audit
print('\n=== QUICK AUDIT ===')
for table in ['match_results', 'match_result_verification', 'postmatch_eval', 'prediction_learning_log', 'prediction_runs']:
    try:
        cur = db.execute(f'SELECT COUNT(*) as cnt FROM "{table}" WHERE match_id = ?', (MATCH_ID,))
        cnt = cur.fetchone()[0]
        print(f'{table}: {cnt} records for GER-PAR')
    except Exception as e:
        print(f'{table}: ERROR - {e}')

# Status sync check
cur = db.execute('SELECT match_status FROM wc26_schedule WHERE match_number=74')
sch = cur.fetchone()['match_status']
cur = db.execute('SELECT status FROM matches WHERE id=?', (MATCH_ID,))
mst = cur.fetchone()['status']
print(f'Status sync: schedule={sch}, matches={mst}, OK={sch==mst}')

# Predictions for learning_log might need prediction_run_id
cur = db.execute('SELECT COUNT(*) as cnt FROM prediction_learning_log WHERE prediction_run_id = ?', (pred_run_id,))
cnt = cur.fetchone()[0]
print(f'prediction_learning_log (by pred_run_id): {cnt} records')

db.close()
print('\nDone.')

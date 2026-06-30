#!/usr/bin/env python
"""Brazil vs Japan post-match review + self-evolution — DB updates only."""
import sqlite3, sys, io, uuid, json, math
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
db = sqlite3.connect('backend/data/local_stage2.db')
db.row_factory = sqlite3.Row

MATCH_ID = '2d5c9c40355d46f7b1a05283027054af'
PRED_RUN_ID = 'df793a8595894a07bfe8069ab7b729d3'
NOW = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

# ============================================================
# STEP 1: Update wc26_schedule
# ============================================================
print('=== STEP 1: Update wc26_schedule ===')
db.execute('''
UPDATE wc26_schedule
SET match_status = 'FINISHED', home_goals = 2, away_goals = 1
WHERE match_number = 76
''')
cur = db.execute('SELECT match_number, home_team, away_team, match_status, home_goals, away_goals FROM wc26_schedule WHERE match_number=76')
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
''', (mr_id, MATCH_ID, 2, 1, NOW))
cur = db.execute('SELECT * FROM match_results WHERE match_id = ?', (MATCH_ID,))
r = cur.fetchone()
print(f'match_results inserted: {dict(r)}')

# ============================================================
# STEP 4: Insert match_result_verification (3 sources)
# ============================================================
print('\n=== STEP 4: Insert verification records ===')
sources = [
    ('Xinhua News (新华网)', 1, 'https://english.news.cn/20260630/c2cc735df0944c03b47306f6042c41ef/c.html'),
    ('NHK World-Japan', 1, 'https://www3.nhk.or.jp/nhkworld/en/news/20260630_101/'),
    ('People Daily (人民网)', 1, 'https://www.peopleapp.com/column/30052523368-500007572156'),
]
verif_ids = []
for src_name, tier, url in sources:
    vid = uuid.uuid4().hex[:32]
    verif_ids.append(vid)
    db.execute('''
    INSERT INTO match_result_verification (id, match_id, home_goals, away_goals, source_name, source_tier, match_status_at_source, is_consensus, notes, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, 'FINISHED', 1, ?, ?, ?)
    ''', (vid, MATCH_ID, 2, 1, src_name, tier, url, NOW, NOW))

cur = db.execute('SELECT id, source_name, source_tier, is_consensus FROM match_result_verification WHERE match_id=?', (MATCH_ID,))
for r in cur.fetchall():
    print(f'  verification: {dict(r)}')

# ============================================================
# STEP 5: Calculate post-match evaluation metrics
# ============================================================
print('\n=== STEP 5: Post-match evaluation ===')

# Prediction probabilities (from DB)
p_home = 0.4952
p_draw = 0.2078
p_away = 0.2970

# Actual outcome: home win
o_home, o_draw, o_away = 1, 0, 0

# Brier Score (3-outcome, normalized)
se_home = (o_home - p_home)**2
se_draw = (o_draw - p_draw)**2
se_away = (o_away - p_away)**2
brier_sum = se_home + se_draw + se_away
brier = brier_sum / 3
print(f'Brier Score = ({se_home:.4f} + {se_draw:.4f} + {se_away:.4f}) / 3 = {brier_sum:.4f} / 3 = {brier:.4f}')

# LogLoss (multi-class)
logloss = -(o_home * math.log(max(p_home, 1e-10)))
print(f'LogLoss = -ln({p_home}) = {logloss:.4f}')

# RPS (Ranked Probability Score)
cum_pred_home = p_home
cum_pred_hd = p_home + p_draw
rps = ((cum_pred_home - o_home)**2 + (cum_pred_hd - (o_home + o_draw))**2) / 2
print(f'RPS = ({((cum_pred_home-o_home)**2):.4f} + {((cum_pred_hd-1)**2):.4f}) / 2 = {rps:.4f}')

# Score hit check
exact_score_hit = False  # 2-1 not in top3 [1-1, 1-0, 0-1]
top3_hit = False
print(f'Exact Score Hit: {exact_score_hit}')
print(f'Top-3 Hit: {top3_hit}')

# Calibration bucket (decile 0-9)
calibration_bucket = int(p_home * 10)
print(f'Calibration bucket: {calibration_bucket}')

# ============================================================
# Component direction assessment
# ============================================================
print('\n=== Component Directions ===')
components = {
    'DC':       (0.375, 0.279, 0.346, 'Brazil'),
    'Enhancer': (0.105, 0.191, 0.704, 'Japan'),
    'Weibull':  (0.084, 0.313, 0.603, 'Japan'),
    'NegBin':   (0.400, 0.228, 0.372, 'Brazil'),
    'Elo':      (0.378, 0.240, 0.383, 'Japan'),
    'Pi':       (0.453, 0.205, 0.342, 'Brazil'),
    'Market':   (0.563, 0.249, 0.187, 'Brazil'),
}

correct = 0
comp_briers = {}
for name, (ph, pd, pa, direction) in components.items():
    predicted_dir = 'home' if ph > pa else ('away' if pa > ph else 'draw')
    actual_dir = 'home'
    is_correct = (predicted_dir == actual_dir)
    if is_correct:
        correct += 1

    # Component Brier
    c_brier = ((1-ph)**2 + (0-pd)**2 + (0-pa)**2) / 3
    comp_briers[name] = c_brier
    status = 'OK' if is_correct else 'WRONG'
    marker = '+' if is_correct else '-'
    print(f'  [{marker}] {name}: {ph:.1%}/{pd:.1%}/{pa:.1%} -> {predicted_dir} {status} | Brier={c_brier:.4f}')

print(f'  Direction: {correct}/7 correct ({correct/7:.0%})')

# Pre-market assessment
pre_market_brier = ((1-0.322)**2 + (0-0.253)**2 + (0-0.425)**2) / 3
print(f'\n  Pre-market Brier: {pre_market_brier:.4f} (Japan favored - WRONG)')
print(f'  Final Brier: {brier:.4f} (Brazil favored - CORRECT)')
print(f'  Market+Calibration flipped direction: Japan(42.5%) -> Brazil(49.5%)')

# ============================================================
# STEP 6: Insert postmatch_eval
# ============================================================
print('\n=== STEP 6: Insert postmatch_eval ===')
eval_id = uuid.uuid4().hex[:32]
actual_result = 'H'

notes = (
    "Brazil 2-1 Japan (HT 0-1). "
    "Japan scored first (Kaishu Sano 29min), Brazil equalized (Casemiro 56min), "
    "Martinelli 90+6min stoppage-time winner. "
    "4/7 components correct direction. Pre-market favored Japan (42.5%), "
    "market+calibration correctly flipped to Brazil (49.5%). "
    "Score matrix missed 2-1 (top3: 1-1, 1-0, 0-1). "
    "Enhancer (70.4% Japan) and Weibull (60.3% Japan) extreme anti-consensus both wrong. "
    "RPS=0.1715, LogLoss=0.7030."
)

db.execute('''
INSERT INTO postmatch_eval (id, prediction_run_id, actual_home_goals, actual_away_goals,
    actual_result, brier_score, log_loss, exact_score_hit, top3_hit,
    calibration_bucket, notes, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
''', (eval_id, PRED_RUN_ID, 2, 1, actual_result, brier, logloss,
      exact_score_hit, top3_hit, calibration_bucket, notes, NOW))

cur = db.execute('SELECT * FROM postmatch_eval WHERE id=?', (eval_id,))
r = cur.fetchone()
print(f'postmatch_eval inserted: {dict(r)}')

# ============================================================
# STEP 7: Insert prediction_learning_log
# ============================================================
print('\n=== STEP 7: Insert prediction_learning_log ===')
learning_id = uuid.uuid4().hex[:32]

error_magnitude = brier * 3  # sum of squared errors
error_direction = 'correct_home'
model_was_right = True

dc_marginal = comp_briers['DC'] - brier
enhancer_marginal = comp_briers['Enhancer'] - brier
elo_marginal = comp_briers['Elo'] - brier
market_marginal = comp_briers['Market'] - brier

context_tags = {
    'stage': 'Round of 32',
    'match_type': 'knockout',
    'component_direction': '4/7',
    'winner': 'Brazil',
    'stoppage_time_winner': True,
    'comeback': True,
    'pre_market_favored': 'Japan',
    'final_favored': 'Brazil',
    'direction_flipped_by_market': True,
    'score': '2-1'
}

db.execute('''
INSERT INTO prediction_learning_log (id, match_id, prediction_run_id,
    error_magnitude, error_direction, model_was_right, status,
    dc_marginal, enhancer_marginal, elo_marginal, market_marginal,
    context_tags, created_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?)
''', (learning_id, MATCH_ID, PRED_RUN_ID,
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
# STEP 8: Determine if weights need adjusting
# ============================================================
print('\n=== STEP 8: Weight adjustment assessment ===')
print('Enhancer: WRONG direction again (70.4% Japan). 14-match accuracy: 29% -> still poor')
print('Weibull: WRONG direction (60.3% Japan). Anti-consensus extreme wrong.')
print('Market: CORRECT. Critical for flipping pre-market direction.')
print('Calibration: Effective - flipped pre-market Japan 42.5% -> final Brazil 49.5%')
print()
print('RECOMMENDATION: No weight change needed.')
print('- Enhancer already suppressed (10% weight, effective ~6.5%)')
print('- Weibull already at 10%')
print('- Market performed crucial corrective role - no change')
print('- Calibration performed well - no change')
print('- Brier=0.1287 is GOOD (below 0.15 threshold)')

# ============================================================
# COMMIT
# ============================================================
db.commit()
print('\n=== ALL DB UPDATES COMMITTED ===')
print(f'match_results id: {mr_id}')
print(f'postmatch_eval id: {eval_id}')
print(f'learning_log id: {learning_id}')
print(f'verification ids: {verif_ids}')

# Quick audit
print('\n=== QUICK AUDIT ===')
for table in ['match_results', 'match_result_verification', 'postmatch_eval', 'prediction_learning_log']:
    cur = db.execute(f'SELECT COUNT(*) as cnt FROM {table} WHERE match_id = ?', (MATCH_ID,))
    cnt = cur.fetchone()[0]
    print(f'{table}: {cnt} records for Brazil-Japan')

# Check wc26_schedule and matches status consistency
cur = db.execute('SELECT match_status FROM wc26_schedule WHERE match_number=76')
sch_status = cur.fetchone()['match_status']
cur = db.execute('SELECT status FROM matches WHERE id=?', (MATCH_ID,))
match_status = cur.fetchone()['status']
print(f'wc26_schedule status: {sch_status} | matches status: {match_status} | Consistent: {sch_status == match_status}')

db.close()
print('\nDone.')

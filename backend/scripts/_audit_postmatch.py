"""Audit: which predicted WC26 matches still need postmatch review + self-evolution.

Links wc26_schedule -> matches -> match_results -> prediction_learning_log.
"""
import sqlite3
import os

DB = os.path.join(os.path.dirname(__file__), '..', 'data', 'local_stage2.db')
db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

# ── 1. Build team_id -> team_name mapping from wc26_schedule ──
# (since matches table uses team_id, we match by date+stage)
team_names = {}
for r in db.execute('SELECT DISTINCT home_team, away_team FROM wc26_schedule').fetchall():
    pass  # just confirming schema

# ── 2. Get all FINISHED matches from wc26_schedule ──
print('=== WC26 FINISHED MATCHES IN wc26_schedule ===')
wc26 = db.execute('''
    SELECT match_number, home_team, away_team, home_goals, away_goals,
           match_date, stage, group_name
    FROM wc26_schedule
    WHERE match_status = "FINISHED"
    ORDER BY match_number
''').fetchall()
print(f"Total FINISHED in wc26_schedule: {len(wc26)}")

# ── 3. Build match_id -> score mapping from match_results ──
mr_map = {}
for r in db.execute('SELECT match_id, home_goals, away_goals FROM match_results').fetchall():
    mr_map[r['match_id']] = (r['home_goals'], r['away_goals'])

# ── 4. Get WC26 from matches table with their results ──
print('\n=== WC26 matches table entries (status finished/FINISHED) ===')
sql_matches = db.execute('''
    SELECT m.id, m.external_id, m.home_team_id, m.away_team_id, m.match_date,
           m.status, m.stage
    FROM matches m
    WHERE m.competition LIKE "%World Cup 2026%"
      AND m.status IN ("finished", "FINISHED")
    ORDER BY m.match_date
''').fetchall()
print(f"Total finished in matches table: {len(sql_matches)}")

# ── 5. Get prediction_learning_log with all details ──
print('\n=== ALL prediction_learning_log entries (WC26 only) ===')
pll_rows = db.execute('''
    SELECT pll.match_id, pll.status, pll.error_magnitude,
           pll.dc_marginal, pll.enhancer_marginal, pll.elo_marginal,
           pll.market_marginal, pll.signal_marginal,
           pll.prediction_run_id
    FROM prediction_learning_log pll
    ORDER BY pll.created_at
''').fetchall()
print(f"Total learning logs: {len(pll_rows)}")

# Build set of match_ids that have learning logs
pll_match_ids = set()
for r in pll_rows:
    pll_match_ids.add(r['match_id'])

# ── 6. Get prediction_runs count per match_id ──
pr_counts = {}
for r in db.execute('SELECT match_id, COUNT(*) as cnt FROM prediction_runs GROUP BY match_id').fetchall():
    pr_counts[r['match_id']] = r['cnt']

# ── 7. Cross-reference: which matches have predictions but no learning log? ──
# We need to match wc26_schedule -> matches table -> check prediction_runs
# Strategy: match by date + team names

print('\n' + '='*100)
print('MATCH-BY-MATCH AUDIT: WC26 FINISHED GAMES')
print('='*100)
print(f"{'#':4s} {'Date':10s} {'Home':20s} | {'Score':5s} | {'Away':20s} | Pred | Learn | Eval | Status")
print('-'*100)

no_learning = []
no_prediction = []
no_result = []
missing_data = []

for m in wc26:
    mn = m['match_number']
    dt = m['match_date']
    home = m['home_team']
    away = m['away_team']
    hg = m['home_goals']
    ag = m['away_goals']
    score = f"{hg}-{ag}" if hg is not None else "?-?"

    if hg is None:
        no_result.append(m)

    # Find corresponding match in matches table by date + external_id pattern
    # external_id format: seed_2026_group_{group}_{match_num}
    grp = (m['group_name'] or '').lower().replace('group ', '')
    found_matches = []
    for sm in sql_matches:
        if sm['match_date'] == m['match_date']:
            found_matches.append(sm)

    match_id = None
    has_result = False
    has_learning = False
    has_pred = False
    learn_status = "-"

    if found_matches:
        # Try to match by team names through wc26_schedule team -> matches team_id
        # Since we don't have team_id -> name mapping easily, match by date+stage
        for fm in found_matches:
            mid = fm['id']
            # Check if this match_id has a result
            if mid in mr_map:
                mg_hg, mg_ag = mr_map[mid]
                if hg is not None and mg_hg == hg and mg_ag == ag:
                    match_id = mid
                    has_result = True
                    break
                elif hg is not None:
                    # Score mismatch — might not be this match
                    continue
                else:
                    match_id = mid
                    has_result = True
                    break
            else:
                # No result in match_results — but could still be the right match
                if match_id is None:
                    match_id = mid

    # Check for predictions (check wc26_schedule match_number against prediction_snapshots)
    # prediction_runs may have a different ID scheme. Let's check if there are PRs linked to the match_id

    # Check learning log
    if match_id and match_id in pll_match_ids:
        has_learning = True
        for r in pll_rows:
            if r['match_id'] == match_id:
                learn_status = r['status']
                break

    # Count predictions linked to this match_id
    pred_count = 0
    if match_id:
        # Check prediction_runs (match_id is stored differently)
        pred_count = pr_counts.get(match_id, 0)
    if pred_count > 0:
        has_pred = True

    flags = ""
    flags += "P" if has_pred else "-"
    flags += "L" if has_learning else "-"
    flags += "R" if has_result else "-"

    if not has_learning and has_pred:
        no_learning.append(dict(m, match_id=match_id, pred_count=pred_count))
    if not has_pred:
        no_prediction.append(m)

    print(f"{mn:4d} {dt} {home:20s} | {score:5s} | {away:20s} | {flags:4s} | {learn_status:20s}")

print(f'\n{"─"*100}')
print(f'TOTAL: {len(wc26)} finished matches')
print(f'  With predictions: {len(wc26) - len(no_prediction)}')
print(f'  Without predictions: {len(no_prediction)}')
print(f'  Missing results: {len(no_result)}')
print(f'  With predictions but NO learning log: {len(no_learning)}')

if no_learning:
    print(f'\n=== MATCHES NEEDING POST-MATCH REVIEW + SELF-EVOLUTION ===')
    for m in no_learning:
        hg = m['home_goals']
        ag = m['away_goals']
        score = f"{hg}-{ag}" if hg is not None else "?-?"
        print(f"  #{m['match_number']:3d} {m['match_date']} {m['home_team']:22s} {score:5s} {m['away_team']:22s} ({m['stage']}) [preds={m['pred_count']}]")

if no_prediction:
    print(f'\n=== MATCHES WITHOUT PREDICTIONS ===')
    for m in no_prediction:
        print(f"  #{m['match_number']:3d} {m['match_date']} {m['home_team']} vs {m['away_team']} ({m['stage']})")

if no_result:
    print(f'\n=== MATCHES WITHOUT SCORES (need to fetch results) ===')
    for m in no_result:
        print(f"  #{m['match_number']:3d} {m['match_date']} {m['home_team']} vs {m['away_team']} ({m['stage']})")

# ── 8. Check for upcoming matches with predictions but not yet finished ──
print(f'\n=== UPCOMING WC26 MATCHES (SCHEDULED) ===')
scheduled = db.execute('''
    SELECT match_number, home_team, away_team, match_date, stage
    FROM wc26_schedule
    WHERE match_status = "SCHEDULED"
    ORDER BY match_number
''').fetchall()
print(f"Total SCHEDULED: {len(scheduled)}")

# ── 9. postmatch_eval table check ──
print(f'\n=== postmatch_eval records ===')
pe_count = db.execute('SELECT COUNT(*) FROM postmatch_eval').fetchone()[0]
print(f"Total postmatch_eval records: {pe_count}")

# ── 10. Reports directory check ──
import glob
report_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'reports', 'postmatch')
if os.path.isdir(report_dir):
    md_files = glob.glob(os.path.join(report_dir, '*.md'))
    json_files = glob.glob(os.path.join(report_dir, '*.json'))
    print(f'\n=== Postmatch report files ({report_dir}) ===')
    print(f"  Markdown reports: {len(md_files)}")
    for f in sorted(md_files):
        print(f"    {os.path.basename(f)}")
    print(f"  JSON data files: {len(json_files)}")
    for f in sorted(json_files):
        print(f"    {os.path.basename(f)}")

# ── 11. Check prediction_snapshots for WC26 ──
print(f'\n=== WC26 prediction_snapshots ===')
ps_count = db.execute('''
    SELECT COUNT(*) FROM prediction_snapshots
    WHERE home_team IN (SELECT DISTINCT home_team FROM wc26_schedule)
''').fetchone()[0]
print(f"  WC26 snapshots (by team name match): {ps_count}")

# ── 12. Check matches table: how many have results but status is wrong ──
print(f'\n=== Data consistency checks ===')
has_result_count = db.execute('''
    SELECT COUNT(*) FROM matches m
    JOIN match_results mr ON m.id = mr.match_id
    WHERE m.competition LIKE "%World Cup 2026%"
''').fetchone()[0]
print(f"  WC26 matches with match_results: {has_result_count}")

finished_with_result = db.execute('''
    SELECT COUNT(*) FROM matches m
    JOIN match_results mr ON m.id = mr.match_id
    WHERE m.competition LIKE "%World Cup 2026%"
      AND m.status IN ("finished", "FINISHED")
''').fetchone()[0]
print(f"  WC26 finished + has result: {finished_with_result}")

not_finished_with_result = db.execute('''
    SELECT COUNT(*) FROM matches m
    JOIN match_results mr ON m.id = mr.match_id
    WHERE m.competition LIKE "%World Cup 2026%"
      AND m.status NOT IN ("finished", "FINISHED")
''').fetchone()[0]
print(f"  WC26 NOT finished but has result: {not_finished_with_result}")

db.close()

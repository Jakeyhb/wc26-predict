"""Quick status check for WC26 knockout preparation."""
import sqlite3, os

DB = os.path.join(os.path.dirname(__file__), '..', 'data', 'local_stage2.db')
db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

# ── 1. Summary ──
print('=== 系统总体状态 ===')
print(f'  预测运行: {db.execute("SELECT COUNT(*) FROM prediction_runs").fetchone()[0]}')
print(f'  预测快照: {db.execute("SELECT COUNT(*) FROM prediction_snapshots").fetchone()[0]}')
print(f'  学习日志: {db.execute("SELECT COUNT(*) FROM prediction_learning_log").fetchone()[0]}')
print(f'  赛后评估: {db.execute("SELECT COUNT(*) FROM postmatch_eval").fetchone()[0]}')

# Learning status
print('\n=== 学习日志状态 ===')
for r in db.execute('SELECT status, COUNT(*) as cnt FROM prediction_learning_log GROUP BY status ORDER BY cnt DESC'):
    print(f'  {r["status"]}: {r["cnt"]}')

# ── 2. WC26 matches status ──
print('\n=== WC26 matches 状态 ===')
for r in db.execute("SELECT status, COUNT(*) as cnt FROM matches WHERE competition LIKE '%World Cup 2026%' GROUP BY status"):
    print(f'  {r["status"]}: {r["cnt"]}')

# ── 3. Prediction by match status ──
wc_pred = db.execute('''SELECT m.status, COUNT(*) as cnt
    FROM prediction_runs pr JOIN matches m ON pr.match_id = m.id
    WHERE m.competition LIKE "%World Cup 2026%"
    GROUP BY m.status''').fetchall()
print('\n=== WC26 预测覆盖 ===')
for r in wc_pred:
    print(f'  {r["status"]}: {r["cnt"]} predictions')

# ── 4. Upcoming group stage (not yet started) ──
print('\n=== 剩余小组赛 (SCHEDULED, Group Stage) ===')
gs = db.execute('''SELECT match_number, home_team, away_team, match_date, group_name
    FROM wc26_schedule
    WHERE match_status="SCHEDULED" AND stage="Group Stage"
    ORDER BY match_date, match_number''').fetchall()
print(f'  剩余: {len(gs)} 场')
for r in gs:
    mn = r['match_number'] or '?'
    dt = r['match_date'] or '?'
    ht = r['home_team'] or '(?)'
    at = r['away_team'] or '(?)'
    gn = r['group_name'] or ''
    print(f'    #{mn} {dt} {ht} vs {at} [{gn}]')

# ── 5. Knockout schedule ──
print('\n=== 淘汰赛赛程 ===')
ko = db.execute('''SELECT match_number, home_team, away_team, match_date, stage, group_name
    FROM wc26_schedule
    WHERE match_status="SCHEDULED" AND stage != "Group Stage" AND stage IS NOT NULL
    ORDER BY match_date, match_number''').fetchall()
print(f'  总计: {len(ko)} 场')
for r in ko:
    mn = r['match_number'] or '?'
    dt = r['match_date'] or '(未定日期)'
    ht = r['home_team'] or '(待定)'
    at = r['away_team'] or '(待定)'
    st = r['stage'] or '?'
    gn = r['group_name'] or ''
    print(f'    #{mn} {dt} {ht:28s} vs {at:28s} ({st}) [{gn}]')

# ── 6. Matches in matches table that need predictions ──
print('\n=== matches表待预测比赛 ===')
no_pred = db.execute('''SELECT m.id, m.home_team_id, m.away_team_id, m.match_date, m.stage, m.status
    FROM matches m
    WHERE m.competition LIKE "%World Cup 2026%"
    AND m.id NOT IN (SELECT DISTINCT match_id FROM prediction_runs)
    ORDER BY m.match_date''').fetchall()
print(f'  无预测记录: {len(no_pred)} 场')
for r in no_pred:
    dt = r['match_date'] or '?'
    st = r['stage'] or '?'
    print(f'    {r["id"][:40]} {dt} {r["home_team_id"]} vs {r["away_team_id"]} ({st}) [{r["status"]}]')

db.close()

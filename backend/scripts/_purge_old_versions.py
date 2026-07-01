"""Delete ALL pre-v4.x artifacts from the database."""
import sqlite3, os

DB = os.path.join(os.path.dirname(__file__), '..', 'data', 'local_stage2.db')
db = sqlite3.connect(DB)

print('=== PRE-DELETE STATE ===')
for tbl in ['prediction_runs', 'prediction_snapshots', 'prediction_learning_log', 'postmatch_eval']:
    cnt = db.execute(f'SELECT COUNT(*) FROM {tbl}').fetchone()[0]
    print(f'  {tbl}: {cnt}')

# ── 1. Null out prediction_run_id in active learning logs that point to old runs ──
old_pr_ids = [r[0] for r in db.execute(
    'SELECT id FROM prediction_runs WHERE model_version NOT LIKE "4.%"'
).fetchall()]

if old_pr_ids:
    placeholders = ','.join('?' * len(old_pr_ids))
    updated = db.execute(
        f'UPDATE prediction_learning_log SET prediction_run_id = NULL WHERE prediction_run_id IN ({placeholders})',
        old_pr_ids
    ).rowcount
    print(f'\nNulled prediction_run_id in {updated} learning logs')

# ── 2. Delete old postmatch_eval ──
if old_pr_ids:
    placeholders = ','.join('?' * len(old_pr_ids))
    deleted_pe = db.execute(
        f'DELETE FROM postmatch_eval WHERE prediction_run_id IN ({placeholders})',
        old_pr_ids
    ).rowcount
    print(f'Deleted {deleted_pe} old postmatch_eval records')

# ── 3. Delete old prediction_runs ──
deleted_pr = db.execute(
    'DELETE FROM prediction_runs WHERE model_version NOT LIKE "4.%"'
).rowcount
print(f'Deleted {deleted_pr} old prediction_runs')

# ── 4. Delete old prediction_snapshots ──
deleted_snaps = db.execute(
    'DELETE FROM prediction_snapshots WHERE model_version NOT LIKE "4.%"'
).rowcount
print(f'Deleted {deleted_snaps} old prediction_snapshots')

db.commit()

# ── 5. Verify ──
print('\n=== POST-DELETE STATE ===')
for tbl in ['prediction_runs', 'prediction_snapshots', 'prediction_learning_log', 'postmatch_eval']:
    cnt = db.execute(f'SELECT COUNT(*) FROM {tbl}').fetchone()[0]
    print(f'  {tbl}: {cnt}')

print('\n=== Remaining prediction_runs ===')
for r in db.execute('SELECT model_version, run_type, COUNT(*) as cnt FROM prediction_runs GROUP BY model_version, run_type ORDER BY cnt DESC'):
    print(f'  v{r["model_version"]:15s} {r["run_type"]:20s} {r["cnt"]:4d}')

print('\n=== Remaining prediction_snapshots ===')
for r in db.execute('SELECT model_version, COUNT(*) as cnt FROM prediction_snapshots GROUP BY model_version ORDER BY cnt DESC'):
    print(f'  v{r["model_version"]:15s} {r["cnt"]:4d}')

print('\n=== Learning log status ===')
for r in db.execute('SELECT status, COUNT(*) as cnt FROM prediction_learning_log GROUP BY status ORDER BY cnt DESC'):
    print(f'  {r["status"]:35s} {r["cnt"]:4d}')

# Verify: any old version left?
old_left = db.execute('SELECT COUNT(*) FROM prediction_runs WHERE model_version NOT LIKE "4.%"').fetchone()[0]
snaps_old_left = db.execute('SELECT COUNT(*) FROM prediction_snapshots WHERE model_version NOT LIKE "4.%"').fetchone()[0]
print(f'\nOld prediction_runs remaining: {old_left}')
print(f'Old prediction_snapshots remaining: {snaps_old_left}')
if old_left == 0 and snaps_old_left == 0:
    print('ALL CLEAN.')

db.close()

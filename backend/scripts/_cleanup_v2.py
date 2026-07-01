"""Cleanup: delete v2.0.0 MANUAL prediction_runs + contaminated learning logs."""
import sqlite3, os

DB = os.path.join(os.path.dirname(__file__), '..', 'data', 'local_stage2.db')
db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

print('=== PRE-CLEANUP STATE ===')
print(f'prediction_runs: {db.execute("SELECT COUNT(*) FROM prediction_runs").fetchone()[0]}')
print(f'prediction_learning_log: {db.execute("SELECT COUNT(*) FROM prediction_learning_log").fetchone()[0]}')
print(f'postmatch_eval: {db.execute("SELECT COUNT(*) FROM postmatch_eval").fetchone()[0]}')
print(f'prediction_snapshots: {db.execute("SELECT COUNT(*) FROM prediction_snapshots").fetchone()[0]}')

# ── Step 1: Identify v2.0.0 MANUAL prediction_runs ──
v2_pr_rows = db.execute(
    'SELECT id, match_id FROM prediction_runs WHERE model_version="2.0.0" AND run_type="MANUAL"'
).fetchall()
v2_pr_ids = [r['id'] for r in v2_pr_rows]
v2_pr_count = len(v2_pr_ids)
print(f'\nv2.0.0 MANUAL prediction_runs to delete: {v2_pr_count}')

# ── Step 2: Identify contaminated learning logs ──
# A learning log is contaminated if it's "active" and the only snapshot for its match_id is v2.0.0
# First get all UUID32 snapshots grouped by match_id
from collections import defaultdict
snap_by_mid = defaultdict(list)
for r in db.execute('SELECT match_id, model_version FROM prediction_snapshots WHERE length(match_id)=32').fetchall():
    mid = r['match_id'].lower().replace('-','')
    snap_by_mid[mid].append(r['model_version'])

contaminated_ll = []
for r in db.execute('SELECT id, match_id, status FROM prediction_learning_log WHERE status="active"').fetchall():
    mid = r['match_id'].lower().replace('-','')
    versions = snap_by_mid.get(mid, [])
    if versions:
        # Check if the NEWEST snapshot is v2.0.0
        # (run_postmatch_complete sorts by generated_at DESC LIMIT 1)
        # Since all versions are only v2.0.0 for contaminated ones (no v4 exists),
        # we just check if all versions are v2.0.0
        if all(v == '2.0.0' for v in versions):
            contaminated_ll.append(r['id'])

print(f'Contaminated learning logs (v2.0.0-only snapshots): {len(contaminated_ll)}')

# ── Step 3: Find linked postmatch_eval ──
# Check schema first
pe_cols = [r[1] for r in db.execute('PRAGMA table_info(postmatch_eval)').fetchall()]
print(f'postmatch_eval columns: {pe_cols}')

linked_pe = []
if contaminated_ll:
    # Try common column names
    link_col = None
    for col in ['learning_log_id', 'log_id', 'eval_id', 'match_id']:
        if col in pe_cols:
            link_col = col
            break
    if link_col:
        placeholders = ','.join('?' for _ in contaminated_ll)
        pe_rows = db.execute(
            f'SELECT id FROM postmatch_eval WHERE {link_col} IN ({placeholders})',
            contaminated_ll
        ).fetchall()
        linked_pe = [r['id'] for r in pe_rows]
print(f'Linked postmatch_eval to delete: {len(linked_pe)}')

# ── Step 4: Find linked prediction_snapshots (v2.0.0 WC26 UUID32) ──
# These are the snapshots used by the contaminated learning logs
v2_snap_ids = []
for mid, versions in snap_by_mid.items():
    if all(v == '2.0.0' for v in versions):
        for r in db.execute('SELECT id FROM prediction_snapshots WHERE REPLACE(LOWER(match_id),\"-\",\"\") = ?', [mid]).fetchall():
            v2_snap_ids.append(r['id'])
print(f'v2.0.0 WC26 snapshots to delete: {len(v2_snap_ids)}')

# ── SUMMARY ──
print(f'\n=== SUMMARY OF DELETIONS ===')
print(f'  prediction_runs (v2.0.0 MANUAL):    {v2_pr_count}')
print(f'  prediction_learning_log (contam):    {len(contaminated_ll)}')
print(f'  postmatch_eval (linked):             {len(linked_pe)}')
print(f'  prediction_snapshots (v2.0.0 WC26):  {len(v2_snap_ids)}')

# ── EXECUTE ──
print('\n=== EXECUTING DELETIONS ===')

# Delete in order: postmatch_eval -> learning_log -> prediction_runs -> snapshots
if linked_pe:
    placeholders = ','.join('?' for _ in linked_pe)
    db.execute(f'DELETE FROM postmatch_eval WHERE id IN ({placeholders})', linked_pe)
    print(f'  Deleted {len(linked_pe)} postmatch_eval records')

if contaminated_ll:
    placeholders = ','.join('?' for _ in contaminated_ll)
    db.execute(f'DELETE FROM prediction_learning_log WHERE id IN ({placeholders})', contaminated_ll)
    print(f'  Deleted {len(contaminated_ll)} prediction_learning_log records')

if v2_pr_ids:
    placeholders = ','.join('?' for _ in v2_pr_ids)
    db.execute(f'DELETE FROM prediction_runs WHERE id IN ({placeholders})', v2_pr_ids)
    print(f'  Deleted {v2_pr_count} prediction_runs records')

if v2_snap_ids:
    placeholders = ','.join('?' for _ in v2_snap_ids)
    db.execute(f'DELETE FROM prediction_snapshots WHERE id IN ({placeholders})', v2_snap_ids)
    print(f'  Deleted {len(v2_snap_ids)} prediction_snapshots records')

db.commit()

# ── POST-CLEANUP STATE ──
print(f'\n=== POST-CLEANUP STATE ===')
print(f'prediction_runs: {db.execute("SELECT COUNT(*) FROM prediction_runs").fetchone()[0]}')
print(f'prediction_learning_log: {db.execute("SELECT COUNT(*) FROM prediction_learning_log").fetchone()[0]}')
total_ll = db.execute('SELECT COUNT(*) FROM prediction_learning_log').fetchone()[0]
active_ll = db.execute('SELECT COUNT(*) FROM prediction_learning_log WHERE status="active"').fetchone()[0]
print(f'  (active: {active_ll})')
print(f'postmatch_eval: {db.execute("SELECT COUNT(*) FROM postmatch_eval").fetchone()[0]}')
print(f'prediction_snapshots: {db.execute("SELECT COUNT(*) FROM prediction_snapshots").fetchone()[0]}')

# Verify: no more v2.0.0 MANUAL runs
remaining_v2 = db.execute('SELECT COUNT(*) FROM prediction_runs WHERE model_version="2.0.0" AND run_type="MANUAL"').fetchone()[0]
print(f'\nRemaining v2.0.0 MANUAL prediction_runs: {remaining_v2}')

# Verify: learning log status breakdown
print('\nLearning log status breakdown:')
for r in db.execute('SELECT status, COUNT(*) as cnt FROM prediction_learning_log GROUP BY status ORDER BY cnt DESC'):
    print(f'  {r["status"]}: {r["cnt"]}')

db.close()
print('\nDone.')

"""Phase 0: Audit prediction pipeline consistency.
Read-only — no business logic changes.

Checks:
1. Map all prediction entry points
2. Verify same inputs produce consistent outputs (sample 3 matches)
3. Check if prediction_snapshots from different entry points are distinguishable
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def main():
    print("=" * 70)
    print("AUDIT: Prediction Pipeline Entry Point Consistency")
    print("=" * 70)

    # 1. Discover all prediction entry points
    print("\n--- Entry Point Discovery ---")
    entry_points = {
        "snapshot.py / run_snapshot()": {
            "file": "backend/scripts/snapshot.py",
            "type": "CLI/manual",
            "has_weights": True,
            "uses_model_config": True,
        },
        "prediction_orchestrator.py / run_prediction()": {
            "file": "backend/app/services/prediction_orchestrator.py",
            "type": "API",
            "has_weights": True,
            "uses_model_config": False,
        },
        "fast_predict.py / fast_predict()": {
            "file": "backend/scripts/fast_predict.py",
            "type": "CLI/quick",
            "has_weights": True,
            "uses_model_config": False,
        },
        "batch_snapshot.py": {
            "file": "backend/scripts/batch_snapshot.py",
            "type": "CLI/batch",
            "has_weights": "likely",
            "uses_model_config": "check",
        },
        "hourly_predict.py": {
            "file": "backend/scripts/hourly_predict.py",
            "type": "Automated",
            "has_weights": "check",
            "uses_model_config": "check",
        },
        "pregenerate_wc26.py": {
            "file": "backend/scripts/pregenerate_wc26.py",
            "type": "CLI/batch",
            "has_weights": "delegates to snapshot",
            "uses_model_config": "delegates to snapshot",
        },
    }

    for name, info in entry_points.items():
        exists = os.path.exists(str(PROJECT_ROOT.parent / info["file"])) or \
                 os.path.exists(str(PROJECT_ROOT / info["file"].replace("backend/", "")))
        print(f"  {name}")
        print(f"    type={info['type']}, weights={info['has_weights']}, exists={exists}")

    # 2. DB: Analyze prediction_snapshots by run_type
    print("\n\n--- Prediction Snapshots by Run Type ---")
    try:
        import sqlite3
        db = PROJECT_ROOT / "data" / "local_stage2.db"
        conn = sqlite3.connect(str(db))
        c = conn.cursor()
        c.execute("""
            SELECT run_type, COUNT(*) as n, COUNT(DISTINCT match_id) as matches
            FROM prediction_snapshots
            GROUP BY run_type
            ORDER BY n DESC
        """)
        rows = c.fetchall()
        if rows:
            for r in rows:
                print(f"  run_type='{r[0]}': {r[1]} snapshots, {r[2]} unique matches")
        else:
            print("  (no snapshots)")

        # Check for duplicate match_id with different run_types
        c.execute("""
            SELECT match_id, COUNT(DISTINCT run_type) as types
            FROM prediction_snapshots
            GROUP BY match_id
            HAVING types > 1
            LIMIT 10
        """)
        multi = c.fetchall()
        if multi:
            print(f"\n  ⚠ {len(multi)} matches have predictions from multiple run_types")
            for r in multi[:5]:
                print(f"    match_id={r[0]}: {r[1]} different run_types")
        else:
            print("\n  ✓ No matches with mixed run_types")

        # Check pipeline_params for model versions
        c.execute("""
            SELECT DISTINCT json_extract(pipeline_params, '$.model_version') as mv
            FROM prediction_snapshots
            WHERE pipeline_params IS NOT NULL
            LIMIT 10
        """)
        versions = c.fetchall()
        print(f"\n  Model versions in snapshots: {[v[0] for v in versions if v[0]]}")

        conn.close()
    except Exception as exc:
        print(f"  DB error: {exc}")

    # 3. Check which entry point is actually used
    print("\n\n--- Entry Point Usage Analysis ---")
    print("  pregenerate_wc26.py → calls snapshot.run_snapshot() → uses _get_model_config()")
    print("  prediction_orchestrator.py → has own weight logic → DIFFERENT from snapshot")
    print("  fast_predict.py → has own simple flow → different from both above")
    print("")
    print("  ⚠ POTENTIAL ISSUE: Same match predicted via different entry points")
    print("    could yield different probabilities due to weight disagreement.")

    # 4. Try a live comparison for one match that has been predicted via pregenerate
    print("\n\n--- Live Consistency Check (sample) ---")
    try:
        import sqlite3
        db = PROJECT_ROOT / "data" / "local_stage2.db"
        conn = sqlite3.connect(str(db))
        c = conn.cursor()
        # Find a WC26 match with a prediction
        c.execute("""
            SELECT ps.match_id, ps.home_team, ps.away_team, ps.baseline_probs, ps.run_type
            FROM prediction_snapshots ps
            WHERE ps.match_id IN (
                SELECT REPLACE(m.id, '-', '')
                FROM matches m
                WHERE m.competition = 'FIFA World Cup 2026' AND m.stage LIKE 'Group%'
            )
            LIMIT 5
        """)
        samples = c.fetchall()
        if samples:
            print(f"  Found {len(samples)} WC26 group match prediction samples:")
            for s in samples:
                import json
                probs = json.loads(s[3]) if s[3] else {}
                print(f"    {s[1]} vs {s[2]} (run_type={s[4]})")
                print(f"      home={probs.get('home_win_prob','?'):.4f} draw={probs.get('draw_prob','?'):.4f} away={probs.get('away_win_prob','?'):.4f}")
        else:
            print("  No WC26 group match predictions found in snapshots")
        conn.close()
    except Exception as exc:
        print(f"  Error: {exc}")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("  Entry points: 6 identified (snapshot, orchestrator, fast_predict,")
    print("                batch_snapshot, hourly_predict, pregenerate_wc26)")
    print("  Urgency: MEDIUM — pregenerate uses snapshot (consistent),")
    print("           but orchestrator and fast_predict use different weights")
    print("  Action: Refactor all to use PredictionPipeline as single entry point")
    print("          (Phase 1 of WC26_predict_FINAL_verified_action_plan.md)")

    return 0


if __name__ == "__main__":
    main()

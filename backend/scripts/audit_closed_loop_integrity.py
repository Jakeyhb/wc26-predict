#!/usr/bin/env python3
"""Read-only audit for prediction -> result -> learning traceability."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "local_stage2.db"
UUID_RE = re.compile(r"^[0-9a-fA-F-]{32,36}$")


def _count(conn: sqlite3.Connection, query: str) -> int:
    return int(conn.execute(query).fetchone()[0])


def main() -> int:
    conn = sqlite3.connect(str(DB_PATH))
    issues: list[str] = []
    ok: list[str] = []

    print("=" * 72)
    print("AUDIT: Closed-loop Integrity")
    print("=" * 72)

    checks = {
        "prediction_snapshots_empty_match_id": "SELECT COUNT(*) FROM prediction_snapshots WHERE match_id IS NULL OR TRIM(match_id) = ''",
        "pre_match_snapshots_empty_match_id": "SELECT COUNT(*) FROM pre_match_snapshots WHERE match_id IS NULL OR TRIM(match_id) = ''",
        "learning_logs_missing_prediction_run_id": "SELECT COUNT(*) FROM prediction_learning_log WHERE status = 'active' AND (prediction_run_id IS NULL OR TRIM(prediction_run_id) = '')",
        "market_odds_unlinked": "SELECT COUNT(*) FROM market_odds WHERE match_id IS NULL OR TRIM(match_id) = ''",
    }
    for label, query in checks.items():
        value = _count(conn, query)
        print(f"{label:42} {value}")
        if value:
            issues.append(f"{label}={value}")
        else:
            ok.append(label)

    linked_postmatch = _count(
        conn,
        """
        SELECT COUNT(*)
        FROM postmatch_eval pe
        JOIN prediction_runs pr ON pr.id = pe.prediction_run_id
        JOIN match_results mr ON REPLACE(CAST(mr.match_id AS TEXT), '-', '') = REPLACE(CAST(pr.match_id AS TEXT), '-', '')
        """,
    )
    total_postmatch = _count(conn, "SELECT COUNT(*) FROM postmatch_eval")
    print(f"postmatch_eval_traceable                 {linked_postmatch}/{total_postmatch}")
    if linked_postmatch != total_postmatch:
        issues.append(f"postmatch_eval_traceable={linked_postmatch}/{total_postmatch}")
    else:
        ok.append("postmatch_eval_traceable")

    active_learning = _count(conn, "SELECT COUNT(*) FROM prediction_learning_log WHERE status = 'active'")
    traceable_learning = _count(
        conn,
        """
        SELECT COUNT(*)
        FROM prediction_learning_log pll
        JOIN prediction_runs pr ON pr.id = pll.prediction_run_id
        WHERE pll.status = 'active'
        """,
    )
    print(f"active_learning_traceable                {traceable_learning}/{active_learning}")
    if traceable_learning != active_learning:
        issues.append(f"active_learning_traceable={traceable_learning}/{active_learning}")
    else:
        ok.append("active_learning_traceable")

    xg_total = _count(conn, "SELECT COUNT(*) FROM match_results")
    xg_real = _count(conn, "SELECT COUNT(*) FROM match_results WHERE home_xg IS NOT NULL AND away_xg IS NOT NULL")
    print(f"match_results_with_real_xg               {xg_real}/{xg_total}")
    if xg_real < max(100, int(xg_total * 0.1)):
        issues.append(f"real_xg_coverage={xg_real}/{xg_total}")
    else:
        ok.append("real_xg_coverage")

    conn.close()

    print("\nSummary:")
    print(f"  OK: {len(ok)}")
    print(f"  Issues: {len(issues)}")
    for issue in issues:
        print(f"   ! {issue}")
    return 2 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())

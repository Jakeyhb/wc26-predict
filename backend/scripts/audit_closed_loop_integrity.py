#!/usr/bin/env python3
"""Read-only audit for prediction -> result -> learning traceability."""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.closed_loop_resolution import QUARANTINE_STATUSES, has_resolution_ledger, ledger_status_counts  # noqa: E402


DB_PATH = PROJECT_ROOT / "data" / "local_stage2.db"
UUID_RE = re.compile(r"^[0-9a-fA-F-]{32,36}$")


def _count(conn: sqlite3.Connection, query: str, params: dict | None = None) -> int:
    return int(conn.execute(query, params or {}).fetchone()[0])


def _quarantined_count(conn: sqlite3.Connection, table: str) -> int:
    if not has_resolution_ledger(conn):
        return 0
    placeholders = ",".join([f":s{i}" for i, _ in enumerate(QUARANTINE_STATUSES)])
    params = {f"s{i}": status for i, status in enumerate(QUARANTINE_STATUSES)}
    params["table"] = table
    return _count(
        conn,
        f"""
        SELECT COUNT(*)
        FROM closed_loop_resolution_ledger
        WHERE entity_table = :table
          AND status IN ({placeholders})
        """,
        params,
    )


def _active_missing_count(conn: sqlite3.Connection, table: str, condition: str) -> int:
    if not has_resolution_ledger(conn):
        return _count(conn, f"SELECT COUNT(*) FROM {table} WHERE {condition}")
    placeholders = ",".join([f":s{i}" for i, _ in enumerate(QUARANTINE_STATUSES)])
    params = {f"s{i}": status for i, status in enumerate(QUARANTINE_STATUSES)}
    params["table"] = table
    return _count(
        conn,
        f"""
        SELECT COUNT(*)
        FROM {table} t
        WHERE ({condition})
          AND NOT EXISTS (
            SELECT 1
            FROM closed_loop_resolution_ledger l
            WHERE l.entity_table = :table
              AND l.entity_id = CAST(t.id AS TEXT)
              AND l.status IN ({placeholders})
          )
        """,
        params,
    )


def main() -> int:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    issues: list[str] = []
    ok: list[str] = []

    print("=" * 72)
    print("AUDIT: Closed-loop Integrity")
    print("=" * 72)

    checks = {
        "prediction_snapshots_empty_match_id": (
            "prediction_snapshots",
            "match_id IS NULL OR TRIM(match_id) = ''",
        ),
        "pre_match_snapshots_empty_match_id": (
            "pre_match_snapshots",
            "match_id IS NULL OR TRIM(match_id) = ''",
        ),
        "learning_logs_missing_prediction_run_id": (
            "prediction_learning_log",
            "status = 'active' AND (prediction_run_id IS NULL OR TRIM(prediction_run_id) = '')",
        ),
        "market_odds_unlinked": (
            "market_odds",
            "match_id IS NULL OR TRIM(match_id) = ''",
        ),
    }
    for label, (table, condition) in checks.items():
        total_missing = _count(conn, f"SELECT COUNT(*) FROM {table} WHERE {condition}")
        quarantined = _quarantined_count(conn, table)
        active_missing = _active_missing_count(conn, table, condition)
        print(f"{label:42} active={active_missing:<4d} total={total_missing:<4d} quarantined={quarantined:<4d}")
        if active_missing:
            issues.append(f"{label} active={active_missing} total={total_missing} quarantined={quarantined}")
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
    quarantined_learning = _quarantined_count(conn, "prediction_learning_log")
    unresolved_learning = max(active_learning - traceable_learning - quarantined_learning, 0)
    print(
        "active_learning_traceable                "
        f"traceable={traceable_learning}/{active_learning} quarantined={quarantined_learning} unresolved={unresolved_learning}"
    )
    if unresolved_learning:
        issues.append(
            f"active_learning_traceable={traceable_learning}/{active_learning}; "
            f"quarantined={quarantined_learning}; unresolved={unresolved_learning}"
        )
    else:
        ok.append("active_learning_traceable_or_quarantined")

    xg_total = _count(conn, "SELECT COUNT(*) FROM match_results")
    xg_real = _count(conn, "SELECT COUNT(*) FROM match_results WHERE home_xg IS NOT NULL AND away_xg IS NOT NULL")
    print(f"match_results_with_real_xg               {xg_real}/{xg_total}")
    if xg_real < max(100, int(xg_total * 0.1)):
        issues.append(f"real_xg_coverage={xg_real}/{xg_total}")
    else:
        ok.append("real_xg_coverage")

    ledger_counts = ledger_status_counts(conn)
    if ledger_counts:
        print("\nResolution ledger:")
        for row in ledger_counts:
            print(f"  {row['entity_table']:28} {row['status']:28} {row['count']:4d}")
    else:
        print("\nResolution ledger: missing or empty")

    conn.close()

    print("\nSummary:")
    print(f"  OK: {len(ok)}")
    print(f"  Issues: {len(issues)}")
    for issue in issues:
        print(f"   ! {issue}")
    return 2 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())

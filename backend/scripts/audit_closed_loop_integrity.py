#!/usr/bin/env python3
"""Read-only audit for prediction -> result -> learning traceability.

The audit treats closed_loop_resolution_ledger as the boundary between active
closed-loop evidence and historical rows that cannot be safely resolved. Rows
that are ledgered as unresolvable_legacy/ambiguous are still reported, but they
do not fail the active closed-loop gate.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.closed_loop_resolution import QUARANTINE_STATUSES, has_resolution_ledger, ledger_status_counts  # noqa: E402


DB_PATH = PROJECT_ROOT / "data" / "local_stage2.db"


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


def _empty_match_id_status(conn: sqlite3.Connection, table: str) -> tuple[int, int, int]:
    if table not in {"prediction_snapshots", "pre_match_snapshots", "market_odds"}:
        raise ValueError(f"unsupported table: {table}")
    raw = _count(
        conn,
        f"""
        SELECT COUNT(*)
        FROM {table}
        WHERE match_id IS NULL OR TRIM(match_id) = ''
        """,
    )
    ledgered = _count(
        conn,
        f"""
        SELECT COUNT(*)
        FROM {table} item
        WHERE (item.match_id IS NULL OR TRIM(item.match_id) = '')
          AND EXISTS (
              SELECT 1
              FROM closed_loop_resolution_ledger ledger
              WHERE ledger.entity_table = '{table}'
                AND ledger.entity_id = item.id
                AND ledger.status IN ('unresolvable_legacy', 'ambiguous')
          )
        """,
    )
    return raw, ledgered, raw - ledgered


def _active_learning_counts(conn: sqlite3.Connection) -> tuple[int, int, int]:
    active = _count(conn, "SELECT COUNT(*) FROM prediction_learning_log WHERE status = 'active'")
    traceable = _count(
        conn,
        """
        SELECT COUNT(*)
        FROM prediction_learning_log pll
        JOIN prediction_runs pr
          ON REPLACE(CAST(pr.id AS TEXT), '-', '') =
             REPLACE(CAST(pll.prediction_run_id AS TEXT), '-', '')
        WHERE pll.status = 'active'
        """,
    )
    missing_run_id = _count(
        conn,
        """
        SELECT COUNT(*)
        FROM prediction_learning_log
        WHERE status = 'active'
          AND (prediction_run_id IS NULL OR TRIM(prediction_run_id) = '')
        """,
    )
    return active, traceable, missing_run_id


def main() -> int:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    issues: list[str] = []
    warnings: list[str] = []
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
        elif total_missing:
            warnings.append(f"{label}: {total_missing} legacy row(s) remain quarantined in resolution ledger")
        else:
            ok.append(label)

    active_learning, traceable_learning, missing_run_id = _active_learning_counts(conn)
    print(f"learning_logs_missing_prediction_run_id    active_missing={missing_run_id}")
    if missing_run_id:
        issues.append(f"learning_logs_missing_prediction_run_id={missing_run_id}")
    else:
        ok.append("learning_logs_missing_prediction_run_id")

    linked_postmatch = _count(
        conn,
        """
        SELECT COUNT(*)
        FROM postmatch_eval pe
        JOIN prediction_runs pr
          ON REPLACE(CAST(pr.id AS TEXT), '-', '') =
             REPLACE(CAST(pe.prediction_run_id AS TEXT), '-', '')
        JOIN match_results mr ON REPLACE(CAST(mr.match_id AS TEXT), '-', '') = REPLACE(CAST(pr.match_id AS TEXT), '-', '')
        """,
    )
    total_postmatch = _count(conn, "SELECT COUNT(*) FROM postmatch_eval")
    print(f"postmatch_eval_traceable                 {linked_postmatch}/{total_postmatch}")
    if linked_postmatch != total_postmatch:
        issues.append(f"postmatch_eval_traceable={linked_postmatch}/{total_postmatch}")
    else:
        ok.append("postmatch_eval_traceable")

    print(f"active_learning_traceable                {traceable_learning}/{active_learning}")
    if traceable_learning != active_learning:
        issues.append(f"active_learning_traceable={traceable_learning}/{active_learning}")
    else:
        ok.append("active_learning_traceable")

    xg_total = _count(conn, "SELECT COUNT(*) FROM match_results")
    xg_real = _count(conn, "SELECT COUNT(*) FROM match_results WHERE home_xg IS NOT NULL AND away_xg IS NOT NULL")
    print(f"match_results_with_real_xg               {xg_real}/{xg_total}")
    if xg_real < max(100, int(xg_total * 0.1)):
        warnings.append(f"real_xg_coverage={xg_real}/{xg_total}")
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
    print(f"  Warnings: {len(warnings)}")
    print(f"  Issues: {len(issues)}")
    for warning in warnings:
        print(f"   - {warning}")
    for issue in issues:
        print(f"   ! {issue}")
    return 2 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())

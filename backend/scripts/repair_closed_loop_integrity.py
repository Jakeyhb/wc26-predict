#!/usr/bin/env python3
"""Repair local closed-loop traceability state.

This script does not invent match IDs. It only:
1. Normalizes prediction_learning_log.prediction_run_id to the canonical
   prediction_runs.id representation used by the local SQLite DB.
2. Applies resolved prediction_run_id values already recorded in
   closed_loop_resolution_ledger.
3. Downgrades legacy learning logs that the ledger marked unresolvable or
   ambiguous so they no longer count as active learning evidence.

Default mode is dry-run. Use --apply to update the local SQLite database.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "local_stage2.db"
REPORT_DIR = PROJECT_ROOT / "reports"
RESOLVER_VERSION = "closed_loop_repair_v1"


@dataclass
class RepairSummary:
    normalized_prediction_run_ids: int = 0
    applied_resolved_run_ids: int = 0
    quarantined_unresolvable_learning_logs: int = 0
    quarantined_ambiguous_learning_logs: int = 0
    active_learning_untraceable_after: int = 0
    active_learning_total_after: int = 0


def _rows(conn: sqlite3.Connection, query: str, params: dict | None = None) -> list[sqlite3.Row]:
    return list(conn.execute(query, params or {}))


def _normalize_prediction_run_ids(conn: sqlite3.Connection, *, apply: bool) -> int:
    rows = _rows(
        conn,
        """
        SELECT pll.id, pr.id AS canonical_run_id
        FROM prediction_learning_log pll
        JOIN prediction_runs pr
          ON REPLACE(CAST(pr.id AS TEXT), '-', '') =
             REPLACE(CAST(pll.prediction_run_id AS TEXT), '-', '')
        WHERE pll.prediction_run_id IS NOT NULL
          AND TRIM(pll.prediction_run_id) <> ''
          AND CAST(pll.prediction_run_id AS TEXT) <> CAST(pr.id AS TEXT)
        """,
    )
    if apply:
        for row in rows:
            conn.execute(
                """
                UPDATE prediction_learning_log
                SET prediction_run_id = :prediction_run_id,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """,
                {"prediction_run_id": row["canonical_run_id"], "id": row["id"]},
            )
    return len(rows)


def _apply_resolved_run_ids(conn: sqlite3.Connection, *, apply: bool) -> int:
    rows = _rows(
        conn,
        """
        SELECT pll.id, pr.id AS canonical_run_id
        FROM closed_loop_resolution_ledger ledger
        JOIN prediction_learning_log pll ON pll.id = ledger.entity_id
        JOIN prediction_runs pr
          ON REPLACE(CAST(pr.id AS TEXT), '-', '') =
             REPLACE(CAST(ledger.resolved_prediction_run_id AS TEXT), '-', '')
        WHERE ledger.entity_table = 'prediction_learning_log'
          AND ledger.status = 'resolved'
          AND ledger.resolved_prediction_run_id IS NOT NULL
          AND TRIM(ledger.resolved_prediction_run_id) <> ''
          AND (
              pll.prediction_run_id IS NULL
              OR TRIM(pll.prediction_run_id) = ''
              OR REPLACE(CAST(pll.prediction_run_id AS TEXT), '-', '') <>
                 REPLACE(CAST(pr.id AS TEXT), '-', '')
          )
        """,
    )
    if apply:
        for row in rows:
            conn.execute(
                """
                UPDATE prediction_learning_log
                SET prediction_run_id = :prediction_run_id,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """,
                {"prediction_run_id": row["canonical_run_id"], "id": row["id"]},
            )
    return len(rows)


def _quarantine_learning_logs(
    conn: sqlite3.Connection,
    *,
    ledger_status: str,
    new_status: str,
    apply: bool,
) -> int:
    rows = _rows(
        conn,
        """
        SELECT pll.id
        FROM prediction_learning_log pll
        JOIN closed_loop_resolution_ledger ledger
          ON ledger.entity_table = 'prediction_learning_log'
         AND ledger.entity_id = pll.id
        WHERE ledger.status = :ledger_status
          AND pll.status = 'active'
        """,
        {"ledger_status": ledger_status},
    )
    if apply:
        now = datetime.now(timezone.utc).isoformat()
        for row in rows:
            conn.execute(
                """
                UPDATE prediction_learning_log
                SET status = :new_status,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """,
                {"new_status": new_status, "id": row["id"]},
            )
            conn.execute(
                """
                UPDATE closed_loop_resolution_ledger
                SET resolver_version = :resolver_version,
                    updated_at = :updated_at
                WHERE entity_table = 'prediction_learning_log'
                  AND entity_id = :id
                """,
                {
                    "resolver_version": RESOLVER_VERSION,
                    "updated_at": now,
                    "id": row["id"],
                },
            )
    return len(rows)


def _count_active_untraceable(conn: sqlite3.Connection) -> int:
    return int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM prediction_learning_log pll
            LEFT JOIN prediction_runs pr
              ON REPLACE(CAST(pr.id AS TEXT), '-', '') =
                 REPLACE(CAST(pll.prediction_run_id AS TEXT), '-', '')
            WHERE pll.status = 'active'
              AND pr.id IS NULL
            """
        ).fetchone()[0]
    )


def _count_active_learning(conn: sqlite3.Connection) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM prediction_learning_log WHERE status = 'active'"
        ).fetchone()[0]
    )


def repair(conn: sqlite3.Connection, *, apply: bool) -> RepairSummary:
    summary = RepairSummary()
    summary.applied_resolved_run_ids = _apply_resolved_run_ids(conn, apply=apply)
    summary.normalized_prediction_run_ids = _normalize_prediction_run_ids(conn, apply=apply)
    summary.quarantined_unresolvable_learning_logs = _quarantine_learning_logs(
        conn,
        ledger_status="unresolvable_legacy",
        new_status="legacy_untraceable",
        apply=apply,
    )
    summary.quarantined_ambiguous_learning_logs = _quarantine_learning_logs(
        conn,
        ledger_status="ambiguous",
        new_status="legacy_ambiguous",
        apply=apply,
    )
    summary.active_learning_untraceable_after = _count_active_untraceable(conn)
    summary.active_learning_total_after = _count_active_learning(conn)
    return summary


def _write_report(summary: RepairSummary, *, apply: bool, db_path: Path) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    mode = "apply" if apply else "dry_run"
    path = REPORT_DIR / f"closed_loop_repair_{ts}_{mode}.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "db_path": str(db_path),
        "summary": asdict(summary),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repair local closed-loop integrity state.")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--apply", action="store_true", help="Apply changes. Default is dry-run.")
    parser.add_argument("--no-report", action="store_true", help="Do not write a JSON report.")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        summary = repair(conn, apply=args.apply)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    finally:
        conn.close()

    print("=" * 72)
    print(f"CLOSED-LOOP REPAIR {'APPLY' if args.apply else 'DRY-RUN'}")
    print("=" * 72)
    for key, value in asdict(summary).items():
        print(f"{key:45} {value}")

    if not args.no_report:
        report_path = _write_report(summary, apply=args.apply, db_path=db_path)
        print(f"\nReport: {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

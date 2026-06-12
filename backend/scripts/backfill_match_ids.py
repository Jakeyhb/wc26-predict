#!/usr/bin/env python3
"""Backfill missing match_id values using the conservative match resolver.

Default mode is dry-run. Use --apply to update the local SQLite database.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.match_resolver import is_uuid_like, resolve_match_id


DB_PATH = PROJECT_ROOT / "data" / "local_stage2.db"


@dataclass
class BackfillResult:
    table: str
    scanned: int = 0
    resolved: int = 0
    unresolved: int = 0
    updated: int = 0


def _rows_for_table(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    if table == "prediction_snapshots":
        return list(
            conn.execute(
                """
                SELECT id, match_id, home_team, away_team, competition, match_time AS kickoff_at, '' AS stage
                FROM prediction_snapshots
                WHERE match_id IS NULL OR TRIM(match_id) = ''
                """
            )
        )
    if table == "pre_match_snapshots":
        return list(
            conn.execute(
                """
                SELECT id, match_id, home_team, away_team, competition, kickoff_at, '' AS stage
                FROM pre_match_snapshots
                WHERE match_id IS NULL OR TRIM(match_id) = ''
                """
            )
        )
    raise ValueError(f"Unsupported table: {table}")


def _backfill_table(
    conn: sqlite3.Connection,
    *,
    table: str,
    apply: bool,
    min_confidence: float,
    limit: int | None,
    db_path: Path,
) -> BackfillResult:
    result = BackfillResult(table=table)
    rows = _rows_for_table(conn, table)
    if limit:
        rows = rows[:limit]

    for row in rows:
        result.scanned += 1
        if is_uuid_like(row["match_id"]):
            continue

        resolved = resolve_match_id(
            home_team=row["home_team"],
            away_team=row["away_team"],
            competition=row["competition"],
            kickoff_at=row["kickoff_at"],
            stage=row["stage"],
            db_path=db_path,
            min_confidence=min_confidence,
        )
        if not resolved:
            result.unresolved += 1
            continue

        result.resolved += 1
        print(
            f"[RESOLVED] {table} {row['id']} -> {resolved.match_id} "
            f"{resolved.home_team} vs {resolved.away_team} "
            f"confidence={resolved.confidence:.2f} reason={resolved.reason}"
        )
        if apply:
            conn.execute(
                f"UPDATE {table} SET match_id = :match_id WHERE id = :id",
                {"match_id": resolved.match_id, "id": row["id"]},
            )
            result.updated += 1

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill prediction snapshot match_id values.")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--table", choices=["all", "prediction_snapshots", "pre_match_snapshots"], default="all")
    parser.add_argument("--apply", action="store_true", help="Actually update the database. Default is dry-run.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when any unresolved rows remain.")
    parser.add_argument("--min-confidence", type=float, default=0.82)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    tables = ["prediction_snapshots", "pre_match_snapshots"] if args.table == "all" else [args.table]
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        results = [
            _backfill_table(
                conn,
                table=table,
                apply=args.apply,
                min_confidence=args.min_confidence,
                limit=args.limit,
                db_path=db_path,
            )
            for table in tables
        ]
        if args.apply:
            conn.commit()
    finally:
        conn.close()

    print("\n" + "=" * 72)
    print(f"MATCH_ID BACKFILL {'APPLY' if args.apply else 'DRY-RUN'}")
    print("=" * 72)
    for item in results:
        print(
            f"{item.table:24} scanned={item.scanned:4d} "
            f"resolved={item.resolved:4d} unresolved={item.unresolved:4d} updated={item.updated:4d}"
        )

    unresolved = sum(item.unresolved for item in results)
    return 2 if args.strict and unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())

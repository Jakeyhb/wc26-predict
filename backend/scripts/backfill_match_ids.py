#!/usr/bin/env python3
"""Backfill/ledger closed-loop identifiers using conservative resolvers.

Default mode is dry-run. Use --apply to update the local SQLite database.
Rows that cannot be resolved safely are written to the resolution ledger so
audits can distinguish active defects from quarantined legacy debt.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.closed_loop_resolution import (  # noqa: E402
    STATUS_AMBIGUOUS,
    STATUS_RESOLVED,
    STATUS_UNRESOLVABLE_LEGACY,
    ResolutionRecord,
    ensure_resolution_ledger,
    ledger_status_counts,
    upsert_resolution,
)
from app.services.match_resolver import is_uuid_like, normalize_uuid, resolve_match_id  # noqa: E402


DB_PATH = PROJECT_ROOT / "data" / "local_stage2.db"


@dataclass
class BackfillResult:
    table: str
    scanned: int = 0
    resolved: int = 0
    ambiguous: int = 0
    unresolved: int = 0
    updated: int = 0
    ledgered: int = 0


def _compact_uuid(value: Any) -> str | None:
    return normalize_uuid(str(value or ""))


def _row_payload(row: sqlite3.Row, keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: row[key] for key in keys if key in row.keys()}


def _record_resolution(
    conn: sqlite3.Connection,
    result: BackfillResult,
    *,
    write_ledger: bool,
    table: str,
    entity_id: str,
    status: str,
    reason: str,
    resolved_match_id: str | None = None,
    resolved_prediction_run_id: str | None = None,
    confidence: float | None = None,
    source_payload: dict[str, Any] | None = None,
) -> None:
    if not write_ledger:
        return
    upsert_resolution(
        conn,
        ResolutionRecord(
            entity_table=table,
            entity_id=str(entity_id),
            status=status,
            reason=reason,
            resolved_match_id=resolved_match_id,
            resolved_prediction_run_id=resolved_prediction_run_id,
            confidence=confidence,
            source_payload=source_payload,
        ),
    )
    result.ledgered += 1


def _rows_for_snapshot_table(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
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
    raise ValueError(f"Unsupported snapshot table: {table}")


def _backfill_snapshot_table(
    conn: sqlite3.Connection,
    *,
    table: str,
    apply: bool,
    min_confidence: float,
    limit: int | None,
    db_path: Path,
) -> BackfillResult:
    result = BackfillResult(table=table)
    rows = _rows_for_snapshot_table(conn, table)
    if limit:
        rows = rows[:limit]

    for row in rows:
        result.scanned += 1
        if is_uuid_like(row["match_id"]):
            continue

        payload = _row_payload(
            row,
            ("id", "match_id", "home_team", "away_team", "competition", "kickoff_at", "stage"),
        )
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
            _record_resolution(
                conn,
                result,
                table=table,
                entity_id=row["id"],
                write_ledger=apply,
                status=STATUS_UNRESOLVABLE_LEGACY,
                reason="no_unique_conservative_match",
                source_payload=payload,
            )
            continue

        result.resolved += 1
        _record_resolution(
            conn,
            result,
            table=table,
            entity_id=row["id"],
            write_ledger=apply,
            status=STATUS_RESOLVED,
            reason=resolved.reason,
            resolved_match_id=resolved.match_id,
            confidence=resolved.confidence,
            source_payload=payload,
        )
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


def _prediction_run_by_id(conn: sqlite3.Connection, prediction_run_id: str | None) -> sqlite3.Row | None:
    compact = _compact_uuid(prediction_run_id)
    if not compact:
        return None
    return conn.execute(
        """
        SELECT id, match_id
        FROM prediction_runs
        WHERE REPLACE(CAST(id AS TEXT), '-', '') = :id
        """,
        {"id": compact},
    ).fetchone()


def _prediction_run_candidates(conn: sqlite3.Connection, match_id: str) -> list[sqlite3.Row]:
    compact = _compact_uuid(match_id)
    if not compact:
        return []
    return list(
        conn.execute(
            """
            SELECT id, match_id, run_type, model_version, as_of_time, created_at
            FROM prediction_runs
            WHERE REPLACE(CAST(match_id AS TEXT), '-', '') = :match_id
            ORDER BY created_at ASC
            """,
            {"match_id": compact},
        )
    )


def _snapshot_match_context(conn: sqlite3.Connection, snapshot_id: str | None) -> sqlite3.Row | None:
    compact = _compact_uuid(snapshot_id)
    if not compact:
        return None
    return conn.execute(
        """
        SELECT id, match_id, home_team, away_team, competition, match_time AS kickoff_at, '' AS stage
        FROM prediction_snapshots
        WHERE REPLACE(CAST(id AS TEXT), '-', '') = :snapshot_id
        """,
        {"snapshot_id": compact},
    ).fetchone()


def _resolve_learning_match_id(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    db_path: Path,
    min_confidence: float,
) -> tuple[str | None, float | None, str, dict[str, Any]]:
    existing_match_id = _compact_uuid(row["match_id"])
    if existing_match_id:
        return existing_match_id, 1.0, "existing_learning_match_id", {}

    pr = _prediction_run_by_id(conn, row["prediction_run_id"])
    if pr is not None:
        match_id = _compact_uuid(pr["match_id"])
        if match_id:
            return match_id, 1.0, "prediction_run_id", {"prediction_run_id": row["prediction_run_id"]}

    snapshot = _snapshot_match_context(conn, row["snapshot_id"])
    if snapshot is None:
        return None, None, "no_snapshot_context", {}

    snapshot_match_id = _compact_uuid(snapshot["match_id"])
    if snapshot_match_id:
        return snapshot_match_id, 0.95, "snapshot_match_id", _row_payload(
            snapshot,
            ("id", "match_id", "home_team", "away_team", "competition", "kickoff_at"),
        )

    resolved = resolve_match_id(
        home_team=snapshot["home_team"],
        away_team=snapshot["away_team"],
        competition=snapshot["competition"],
        kickoff_at=snapshot["kickoff_at"],
        stage=snapshot["stage"],
        db_path=db_path,
        min_confidence=min_confidence,
    )
    if resolved is None:
        return None, None, "snapshot_context_unresolved", _row_payload(
            snapshot,
            ("id", "match_id", "home_team", "away_team", "competition", "kickoff_at"),
        )
    return resolved.match_id, resolved.confidence, f"snapshot_resolver:{resolved.reason}", _row_payload(
        snapshot,
        ("id", "match_id", "home_team", "away_team", "competition", "kickoff_at"),
    )


def _backfill_learning_logs(
    conn: sqlite3.Connection,
    *,
    apply: bool,
    min_confidence: float,
    limit: int | None,
    db_path: Path,
) -> BackfillResult:
    table = "prediction_learning_log"
    result = BackfillResult(table=table)
    rows = list(
        conn.execute(
            """
            SELECT id, match_id, prediction_run_id, snapshot_id, created_at, status
            FROM prediction_learning_log
            WHERE status = 'active'
              AND (
                prediction_run_id IS NULL OR TRIM(prediction_run_id) = ''
                OR match_id IS NULL OR TRIM(match_id) = ''
              )
            """
        )
    )
    if limit:
        rows = rows[:limit]

    for row in rows:
        result.scanned += 1
        payload = _row_payload(row, ("id", "match_id", "prediction_run_id", "snapshot_id", "created_at", "status"))
        match_id, confidence, reason, context = _resolve_learning_match_id(
            conn,
            row,
            db_path=db_path,
            min_confidence=min_confidence,
        )
        payload.update({"context": context})
        if not match_id:
            result.unresolved += 1
            _record_resolution(
                conn,
                result,
                table=table,
                entity_id=row["id"],
                write_ledger=apply,
                status=STATUS_UNRESOLVABLE_LEGACY,
                reason=reason,
                source_payload=payload,
            )
            continue

        candidates = _prediction_run_candidates(conn, match_id)
        if len(candidates) == 1:
            prediction_run_id = _compact_uuid(candidates[0]["id"])
            result.resolved += 1
            _record_resolution(
                conn,
                result,
                table=table,
                entity_id=row["id"],
                write_ledger=apply,
                status=STATUS_RESOLVED,
                reason=f"{reason}+single_prediction_run_for_match",
                resolved_match_id=match_id,
                resolved_prediction_run_id=prediction_run_id,
                confidence=confidence,
                source_payload=payload,
            )
            print(f"[RESOLVED] {table} {row['id']} -> match={match_id} prediction_run={prediction_run_id}")
            if apply:
                conn.execute(
                    """
                    UPDATE prediction_learning_log
                    SET match_id = COALESCE(NULLIF(TRIM(match_id), ''), :match_id),
                        prediction_run_id = :prediction_run_id,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """,
                    {"match_id": match_id, "prediction_run_id": prediction_run_id, "id": row["id"]},
                )
                result.updated += 1
            continue

        if len(candidates) > 1:
            result.ambiguous += 1
            _record_resolution(
                conn,
                result,
                table=table,
                entity_id=row["id"],
                write_ledger=apply,
                status=STATUS_AMBIGUOUS,
                reason=f"{reason}+multiple_prediction_runs_for_match",
                resolved_match_id=match_id,
                confidence=confidence,
                source_payload={**payload, "candidate_count": len(candidates)},
            )
            continue

        result.unresolved += 1
        _record_resolution(
            conn,
            result,
            table=table,
            entity_id=row["id"],
            write_ledger=apply,
            status=STATUS_UNRESOLVABLE_LEGACY,
            reason=f"{reason}+no_prediction_run_for_match",
            resolved_match_id=match_id,
            confidence=confidence,
            source_payload=payload,
        )

    return result


def _snapshot_prefix_from_legacy_run_id(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text.startswith("snapshot_"):
        return None
    prefix = text.removeprefix("snapshot_").strip()
    return prefix or None


def _snapshot_by_prefix(conn: sqlite3.Connection, prefix: str | None) -> tuple[sqlite3.Row | None, int]:
    if not prefix:
        return None, 0
    rows = list(
        conn.execute(
            """
            SELECT id, match_id, home_team, away_team, competition, match_time AS kickoff_at
            FROM prediction_snapshots
            WHERE REPLACE(CAST(id AS TEXT), '-', '') LIKE :prefix
            """,
            {"prefix": f"{prefix.replace('-', '')}%"},
        )
    )
    return (rows[0], len(rows)) if len(rows) == 1 else (None, len(rows))


def _backfill_postmatch_eval(
    conn: sqlite3.Connection,
    *,
    apply: bool,
    limit: int | None,
) -> BackfillResult:
    table = "postmatch_eval"
    result = BackfillResult(table=table)
    rows = list(
        conn.execute(
            """
            SELECT pe.id, pe.prediction_run_id, pe.actual_home_goals, pe.actual_away_goals, pe.actual_result, pe.created_at
            FROM postmatch_eval pe
            LEFT JOIN prediction_runs pr ON pr.id = pe.prediction_run_id
            WHERE pr.id IS NULL
            """
        )
    )
    if limit:
        rows = rows[:limit]

    for row in rows:
        result.scanned += 1
        payload = _row_payload(
            row,
            ("id", "prediction_run_id", "actual_home_goals", "actual_away_goals", "actual_result", "created_at"),
        )

        direct_pr = _prediction_run_by_id(conn, row["prediction_run_id"])
        if direct_pr is not None:
            prediction_run_id = _compact_uuid(direct_pr["id"])
            match_id = _compact_uuid(direct_pr["match_id"])
            result.resolved += 1
            _record_resolution(
                conn,
                result,
                table=table,
                entity_id=row["id"],
                write_ledger=apply,
                status=STATUS_RESOLVED,
                reason="prediction_run_id_exists",
                resolved_match_id=match_id,
                resolved_prediction_run_id=prediction_run_id,
                confidence=1.0,
                source_payload=payload,
            )
            continue

        snapshot_prefix = _snapshot_prefix_from_legacy_run_id(row["prediction_run_id"])
        snapshot, snapshot_count = _snapshot_by_prefix(conn, snapshot_prefix)
        if snapshot_count > 1:
            result.ambiguous += 1
            _record_resolution(
                conn,
                result,
                table=table,
                entity_id=row["id"],
                write_ledger=apply,
                status=STATUS_AMBIGUOUS,
                reason="legacy_snapshot_prefix_multiple_matches",
                source_payload={**payload, "snapshot_prefix": snapshot_prefix, "candidate_count": snapshot_count},
            )
            continue
        if snapshot is None:
            result.unresolved += 1
            _record_resolution(
                conn,
                result,
                table=table,
                entity_id=row["id"],
                write_ledger=apply,
                status=STATUS_UNRESOLVABLE_LEGACY,
                reason="no_prediction_run_or_snapshot_context",
                source_payload=payload,
            )
            continue

        match_id = _compact_uuid(snapshot["match_id"])
        if not match_id:
            result.unresolved += 1
            _record_resolution(
                conn,
                result,
                table=table,
                entity_id=row["id"],
                write_ledger=apply,
                status=STATUS_UNRESOLVABLE_LEGACY,
                reason="snapshot_missing_match_id",
                source_payload={**payload, "snapshot_id": snapshot["id"]},
            )
            continue

        candidates = _prediction_run_candidates(conn, match_id)
        if len(candidates) == 1:
            prediction_run_id = _compact_uuid(candidates[0]["id"])
            result.resolved += 1
            _record_resolution(
                conn,
                result,
                table=table,
                entity_id=row["id"],
                write_ledger=apply,
                status=STATUS_RESOLVED,
                reason="legacy_snapshot_prefix+single_prediction_run_for_match",
                resolved_match_id=match_id,
                resolved_prediction_run_id=prediction_run_id,
                confidence=0.9,
                source_payload={**payload, "snapshot_id": snapshot["id"]},
            )
            print(f"[RESOLVED] {table} {row['id']} -> prediction_run={prediction_run_id}")
            if apply:
                conn.execute(
                    "UPDATE postmatch_eval SET prediction_run_id = :prediction_run_id WHERE id = :id",
                    {"prediction_run_id": prediction_run_id, "id": row["id"]},
                )
                result.updated += 1
            continue

        if len(candidates) > 1:
            result.ambiguous += 1
            _record_resolution(
                conn,
                result,
                table=table,
                entity_id=row["id"],
                write_ledger=apply,
                status=STATUS_AMBIGUOUS,
                reason="legacy_snapshot_prefix+multiple_prediction_runs_for_match",
                resolved_match_id=match_id,
                confidence=0.6,
                source_payload={**payload, "snapshot_id": snapshot["id"], "candidate_count": len(candidates)},
            )
            continue

        result.unresolved += 1
        _record_resolution(
            conn,
            result,
            table=table,
            entity_id=row["id"],
            write_ledger=apply,
            status=STATUS_UNRESOLVABLE_LEGACY,
            reason="legacy_snapshot_prefix+no_prediction_run_for_match",
            resolved_match_id=match_id,
            source_payload={**payload, "snapshot_id": snapshot["id"]},
        )

    return result


def _backfill_market_odds(
    conn: sqlite3.Connection,
    *,
    apply: bool,
    limit: int | None,
) -> BackfillResult:
    table = "market_odds"
    result = BackfillResult(table=table)
    rows = list(
        conn.execute(
            """
            SELECT id, match_id, fetched_at, provider, home_implied_prob, draw_implied_prob, away_implied_prob
            FROM market_odds
            WHERE match_id IS NULL OR TRIM(match_id) = ''
            """
        )
    )
    if limit:
        rows = rows[:limit]

    for row in rows:
        result.scanned += 1
        result.unresolved += 1
        _record_resolution(
            conn,
            result,
            table=table,
            entity_id=row["id"],
            write_ledger=apply,
            status=STATUS_UNRESOLVABLE_LEGACY,
            reason="legacy_market_odds_missing_team_time_context",
            source_payload=_row_payload(
                row,
                ("id", "match_id", "fetched_at", "provider", "home_implied_prob", "draw_implied_prob", "away_implied_prob"),
            ),
        )
    return result


def _write_report(
    *,
    report_dir: Path,
    db_path: Path,
    apply: bool,
    results: list[BackfillResult],
    ledger_counts: list[sqlite3.Row],
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = report_dir / f"closed_loop_backfill_{stamp}_{'apply' if apply else 'dry_run'}.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if apply else "dry_run",
        "db_path": str(db_path),
        "results": [asdict(item) for item in results],
        "ledger_status_counts": [dict(row) for row in ledger_counts],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill closed-loop match_id and prediction_run_id values.")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument(
        "--table",
        choices=[
            "all",
            "prediction_snapshots",
            "pre_match_snapshots",
            "prediction_learning_log",
            "postmatch_eval",
            "market_odds",
        ],
        default="all",
    )
    parser.add_argument("--apply", action="store_true", help="Actually update resolvable data. Default is dry-run.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when any non-ledgered unresolved rows remain.")
    parser.add_argument("--min-confidence", type=float, default=0.82)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--report-dir", default=str(PROJECT_ROOT / "reports"))
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    tables = (
        ["prediction_snapshots", "pre_match_snapshots", "prediction_learning_log", "postmatch_eval", "market_odds"]
        if args.table == "all"
        else [args.table]
    )
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if args.apply:
            ensure_resolution_ledger(conn)
        results: list[BackfillResult] = []
        for table in tables:
            if table in {"prediction_snapshots", "pre_match_snapshots"}:
                results.append(
                    _backfill_snapshot_table(
                        conn,
                        table=table,
                        apply=args.apply,
                        min_confidence=args.min_confidence,
                        limit=args.limit,
                        db_path=db_path,
                    )
                )
            elif table == "prediction_learning_log":
                results.append(
                    _backfill_learning_logs(
                        conn,
                        apply=args.apply,
                        min_confidence=args.min_confidence,
                        limit=args.limit,
                        db_path=db_path,
                    )
                )
            elif table == "postmatch_eval":
                results.append(_backfill_postmatch_eval(conn, apply=args.apply, limit=args.limit))
            elif table == "market_odds":
                results.append(_backfill_market_odds(conn, apply=args.apply, limit=args.limit))
            else:  # pragma: no cover - argparse prevents this.
                raise ValueError(table)

        ledger_counts = ledger_status_counts(conn)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    finally:
        conn.close()

    print("\n" + "=" * 72)
    print(f"CLOSED-LOOP BACKFILL {'APPLY' if args.apply else 'DRY-RUN'}")
    print("=" * 72)
    for item in results:
        print(
            f"{item.table:28} scanned={item.scanned:4d} resolved={item.resolved:4d} "
            f"ambiguous={item.ambiguous:4d} unresolved={item.unresolved:4d} "
            f"updated={item.updated:4d} ledgered={item.ledgered:4d}"
        )

    print("\nLedger:")
    for row in ledger_counts:
        print(f"  {row['entity_table']:28} {row['status']:28} {row['count']:4d}")

    report_path = _write_report(
        report_dir=Path(args.report_dir),
        db_path=db_path,
        apply=args.apply,
        results=results,
        ledger_counts=ledger_counts,
    )
    print(f"\nReport: {report_path}")

    unresolved_without_ledger = sum(item.unresolved + item.ambiguous - item.ledgered for item in results)
    return 2 if args.strict and unresolved_without_ledger > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())

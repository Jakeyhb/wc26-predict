#!/usr/bin/env python3
"""Read-only audit for V3.6 data provenance and coverage.

This script does not ingest data, update rows, or infer missing match links.
It answers a narrower question before Phase 2 data expansion: which data
families have enough traceable, time-aware coverage to be trusted by
walk-forward backtests?
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.closed_loop_resolution import QUARANTINE_STATUSES, has_resolution_ledger  # noqa: E402


DB_PATH = PROJECT_ROOT / "data" / "local_stage2.db"
INJURIES_PATH = PROJECT_ROOT / "data" / "injuries.json"

STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_CRITICAL = "critical"


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    message: str
    metrics: dict[str, Any]


def _count(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> int:
    row = conn.execute(query, params).fetchone()
    return int(row[0] if row else 0)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return _count(
        conn,
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ) > 0


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _safe_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None


def _is_nonempty_json_object(value: Any) -> bool:
    parsed = _safe_json(value)
    return isinstance(parsed, dict) and bool(parsed)


def _quarantined_count(conn: sqlite3.Connection, table: str) -> int:
    if not has_resolution_ledger(conn):
        return 0
    placeholders = ",".join("?" for _ in QUARANTINE_STATUSES)
    return _count(
        conn,
        f"""
        SELECT COUNT(*)
        FROM closed_loop_resolution_ledger
        WHERE entity_table = ?
          AND status IN ({placeholders})
        """,
        (table, *QUARANTINE_STATUSES),
    )


def _active_missing_count(conn: sqlite3.Connection, table: str, condition: str) -> int:
    if not _table_exists(conn, table):
        return 0
    if not has_resolution_ledger(conn):
        return _count(conn, f"SELECT COUNT(*) FROM {table} WHERE {condition}")
    placeholders = ",".join("?" for _ in QUARANTINE_STATUSES)
    return _count(
        conn,
        f"""
        SELECT COUNT(*)
        FROM {table} t
        WHERE ({condition})
          AND NOT EXISTS (
            SELECT 1
            FROM closed_loop_resolution_ledger l
            WHERE l.entity_table = ?
              AND l.entity_id = CAST(t.id AS TEXT)
              AND l.status IN ({placeholders})
          )
        """,
        (table, *QUARANTINE_STATUSES),
    )


def audit_real_xg(conn: sqlite3.Connection, min_xg_coverage: int | None = None) -> Check:
    if not _table_exists(conn, "match_results"):
        return Check(
            name="real_xg_coverage",
            status=STATUS_CRITICAL,
            message="match_results table is missing",
            metrics={},
        )

    total = _count(conn, "SELECT COUNT(*) FROM match_results")
    real = _count(
        conn,
        "SELECT COUNT(*) FROM match_results WHERE home_xg IS NOT NULL AND away_xg IS NOT NULL",
    )
    threshold = min_xg_coverage if min_xg_coverage is not None else max(100, int(total * 0.1))
    coverage = (real / total) if total else 0.0

    by_competition: list[dict[str, Any]] = []
    if _table_exists(conn, "matches"):
        match_columns = _columns(conn, "matches")
        if "competition" in match_columns:
            competition_by_match_id = {
                str(row["id"]).replace("-", ""): row["competition"] or "unknown"
                for row in conn.execute("SELECT id, competition FROM matches")
            }
            grouped: dict[str, dict[str, int]] = {}
            for row in conn.execute("SELECT match_id, home_xg, away_xg FROM match_results"):
                match_id = str(row["match_id"]).replace("-", "")
                competition = competition_by_match_id.get(match_id, "unknown")
                bucket = grouped.setdefault(competition, {"total": 0, "real_xg": 0})
                bucket["total"] += 1
                if row["home_xg"] is not None and row["away_xg"] is not None:
                    bucket["real_xg"] += 1
            by_competition = [
                {"competition": competition, **metrics}
                for competition, metrics in sorted(
                    grouped.items(),
                    key=lambda item: (-item[1]["total"], item[0]),
                )
            ]

    if total == 0:
        status = STATUS_CRITICAL
        message = "match_results is empty; no scored matches can support model learning"
    elif real < threshold:
        status = STATUS_CRITICAL
        message = f"real xG coverage {real}/{total} is below threshold {threshold}"
    else:
        status = STATUS_OK
        message = f"real xG coverage {real}/{total} meets threshold {threshold}"

    return Check(
        name="real_xg_coverage",
        status=status,
        message=message,
        metrics={
            "total": total,
            "real_xg": real,
            "coverage": coverage,
            "threshold": threshold,
            "by_competition": by_competition,
        },
    )


def audit_market_odds(conn: sqlite3.Connection) -> Check:
    if not _table_exists(conn, "market_odds"):
        return Check(
            name="market_odds_provenance",
            status=STATUS_WARN,
            message="market_odds table is missing",
            metrics={},
        )

    columns = _columns(conn, "market_odds")
    total = _count(conn, "SELECT COUNT(*) FROM market_odds")
    linked = _count(
        conn,
        "SELECT COUNT(*) FROM market_odds WHERE match_id IS NOT NULL AND TRIM(match_id) <> ''",
    )
    distinct_matches = _count(
        conn,
        "SELECT COUNT(DISTINCT match_id) FROM market_odds WHERE match_id IS NOT NULL AND TRIM(match_id) <> ''",
    )
    unlinked_total = _count(
        conn,
        "SELECT COUNT(*) FROM market_odds WHERE match_id IS NULL OR TRIM(match_id) = ''",
    )
    active_unlinked = _active_missing_count(conn, "market_odds", "match_id IS NULL OR TRIM(match_id) = ''")
    quarantined = _quarantined_count(conn, "market_odds")

    fetched_at = 0
    provider_count = 0
    latest_fetched_at = None
    if "fetched_at" in columns:
        fetched_at = _count(conn, "SELECT COUNT(*) FROM market_odds WHERE fetched_at IS NOT NULL AND TRIM(fetched_at) <> ''")
        latest_fetched_at = conn.execute("SELECT MAX(fetched_at) FROM market_odds").fetchone()[0]
    if "provider" in columns:
        provider_count = _count(conn, "SELECT COUNT(DISTINCT provider) FROM market_odds WHERE provider IS NOT NULL")

    if total == 0:
        status = STATUS_WARN
        message = "market_odds is empty; market stays unavailable as a shadow benchmark"
    elif active_unlinked:
        status = STATUS_CRITICAL
        message = f"market_odds has {active_unlinked} active unlinked rows"
    elif distinct_matches <= 1:
        status = STATUS_WARN
        message = f"market odds are traceable but sparse: {distinct_matches} linked match(es)"
    else:
        status = STATUS_OK
        message = f"market odds have {linked}/{total} linked rows across {distinct_matches} matches"

    return Check(
        name="market_odds_provenance",
        status=status,
        message=message,
        metrics={
            "total": total,
            "linked": linked,
            "distinct_matches": distinct_matches,
            "unlinked_total": unlinked_total,
            "active_unlinked": active_unlinked,
            "quarantined_unlinked": quarantined,
            "rows_with_fetched_at": fetched_at,
            "latest_fetched_at": latest_fetched_at,
            "provider_count": provider_count,
        },
    )


def audit_pre_match_provenance(conn: sqlite3.Connection) -> Check:
    if not _table_exists(conn, "pre_match_snapshots"):
        return Check(
            name="pre_match_snapshot_provenance",
            status=STATUS_WARN,
            message="pre_match_snapshots table is missing",
            metrics={},
        )

    columns = _columns(conn, "pre_match_snapshots")
    total = _count(conn, "SELECT COUNT(*) FROM pre_match_snapshots")
    with_source_timestamps = 0
    if "source_timestamps" in columns:
        rows = conn.execute("SELECT source_timestamps FROM pre_match_snapshots").fetchall()
        with_source_timestamps = sum(1 for row in rows if _is_nonempty_json_object(row[0]))

    flag_columns = {
        "weather_available": "weather_snapshot",
        "odds_available": "odds_snapshot",
        "lineup_available": "lineup_snapshot",
        "injury_data_available": "injury_records",
        "news_signals_available": "news_signal_ids",
    }
    flag_metrics: dict[str, dict[str, int]] = {}
    missing_provenance_rows = 0
    missing_payload_rows = 0

    selected = ["id"]
    for flag, payload in flag_columns.items():
        if flag in columns:
            selected.append(flag)
        if payload in columns:
            selected.append(payload)
    if "source_timestamps" in columns:
        selected.append("source_timestamps")
    select_clause = ", ".join(dict.fromkeys(selected))

    for flag, payload in flag_columns.items():
        if flag not in columns:
            continue
        available = _count(conn, f"SELECT COUNT(*) FROM pre_match_snapshots WHERE COALESCE({flag}, 0) = 1")
        payload_present = 0
        if payload in columns:
            rows = conn.execute(f"SELECT {payload} FROM pre_match_snapshots WHERE COALESCE({flag}, 0) = 1").fetchall()
            payload_present = sum(1 for row in rows if _safe_json(row[0]) not in (None, [], {}))
        flag_metrics[flag] = {
            "available": available,
            "payload_present": payload_present,
        }

    if total and select_clause:
        for row in conn.execute(f"SELECT {select_clause} FROM pre_match_snapshots"):
            row_dict = dict(row)
            timestamps_present = _is_nonempty_json_object(row_dict.get("source_timestamps"))
            for flag, payload in flag_columns.items():
                if flag not in row_dict or not row_dict.get(flag):
                    continue
                if "source_timestamps" in row_dict and not timestamps_present:
                    missing_provenance_rows += 1
                    break
            for flag, payload in flag_columns.items():
                if flag not in row_dict or payload not in row_dict or not row_dict.get(flag):
                    continue
                if _safe_json(row_dict.get(payload)) in (None, [], {}):
                    missing_payload_rows += 1
                    break

    snapshot_id_metrics = {
        "odds_snapshot_id": 0,
        "weather_snapshot_id": 0,
        "injury_snapshot_id": 0,
    }
    for column in list(snapshot_id_metrics):
        if column in columns:
            snapshot_id_metrics[column] = _count(
                conn,
                f"SELECT COUNT(*) FROM pre_match_snapshots WHERE {column} IS NOT NULL AND TRIM({column}) <> ''",
            )

    if total == 0:
        status = STATUS_WARN
        message = "pre_match_snapshots is empty; no time-aware pre-match state exists"
    elif missing_provenance_rows or missing_payload_rows:
        status = STATUS_WARN
        message = (
            "pre_match_snapshots have available input flags without complete "
            "source timestamps or payloads"
        )
    else:
        status = STATUS_OK
        message = "pre_match snapshot provenance is internally consistent"

    return Check(
        name="pre_match_snapshot_provenance",
        status=status,
        message=message,
        metrics={
            "total": total,
            "with_source_timestamps": with_source_timestamps,
            "missing_provenance_rows": missing_provenance_rows,
            "missing_payload_rows": missing_payload_rows,
            "flags": flag_metrics,
            "snapshot_ids": snapshot_id_metrics,
        },
    )


def audit_injury_provenance(injuries_path: Path) -> Check:
    if not injuries_path.exists():
        return Check(
            name="injury_file_provenance",
            status=STATUS_WARN,
            message=f"injury file is missing: {injuries_path}",
            metrics={"path": str(injuries_path)},
        )

    try:
        payload = json.loads(injuries_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Check(
            name="injury_file_provenance",
            status=STATUS_WARN,
            message=f"injury file could not be parsed: {exc}",
            metrics={"path": str(injuries_path)},
        )

    records = payload if isinstance(payload, list) else payload.get("injuries", [])
    if not isinstance(records, list):
        records = []
    with_source = sum(1 for item in records if isinstance(item, dict) and item.get("source"))
    with_last_updated = sum(1 for item in records if isinstance(item, dict) and item.get("last_updated"))
    teams = sorted(
        {
            str(item.get("team"))
            for item in records
            if isinstance(item, dict) and item.get("team")
        }
    )

    if not records:
        status = STATUS_WARN
        message = "injury file is empty; no player availability signal can be trusted"
    elif with_source < len(records) or with_last_updated < len(records):
        status = STATUS_WARN
        message = "injury records exist but some lack source or last_updated"
    else:
        status = STATUS_OK
        message = "injury records carry source and last_updated provenance"

    return Check(
        name="injury_file_provenance",
        status=status,
        message=message,
        metrics={
            "path": str(injuries_path),
            "records": len(records),
            "with_source": with_source,
            "with_last_updated": with_last_updated,
            "team_count": len(teams),
        },
    )


def audit_lineup_provenance(conn: sqlite3.Connection) -> Check:
    pre_match_total = 0
    pre_match_available = 0
    pre_match_payload = 0
    if _table_exists(conn, "pre_match_snapshots"):
        columns = _columns(conn, "pre_match_snapshots")
        pre_match_total = _count(conn, "SELECT COUNT(*) FROM pre_match_snapshots")
        if "lineup_available" in columns:
            pre_match_available = _count(
                conn,
                "SELECT COUNT(*) FROM pre_match_snapshots WHERE COALESCE(lineup_available, 0) = 1",
            )
        if "lineup_snapshot" in columns:
            rows = conn.execute(
                "SELECT lineup_snapshot FROM pre_match_snapshots WHERE COALESCE(lineup_available, 0) = 1"
            ).fetchall()
            pre_match_payload = sum(1 for row in rows if _safe_json(row[0]) not in (None, [], {}))

    probe_total = 0
    probe_with_lineup = 0
    latest_probe = None
    if _table_exists(conn, "lineup_probe_logs"):
        columns = _columns(conn, "lineup_probe_logs")
        probe_total = _count(conn, "SELECT COUNT(*) FROM lineup_probe_logs")
        if "has_lineup" in columns:
            probe_with_lineup = _count(conn, "SELECT COUNT(*) FROM lineup_probe_logs WHERE COALESCE(has_lineup, 0) = 1")
        if "probed_at" in columns:
            latest_probe = conn.execute("SELECT MAX(probed_at) FROM lineup_probe_logs").fetchone()[0]

    if pre_match_available == 0 and probe_with_lineup == 0:
        status = STATUS_WARN
        message = "lineup data is not yet available in pre-match snapshots or probes"
    elif pre_match_available and pre_match_payload < pre_match_available:
        status = STATUS_WARN
        message = "some snapshots mark lineup_available without a lineup payload"
    else:
        status = STATUS_OK
        message = "lineup provenance has traceable payloads or probe evidence"

    return Check(
        name="lineup_provenance",
        status=status,
        message=message,
        metrics={
            "pre_match_snapshots": pre_match_total,
            "pre_match_lineup_available": pre_match_available,
            "pre_match_lineup_payload": pre_match_payload,
            "probe_logs": probe_total,
            "probe_logs_with_lineup": probe_with_lineup,
            "latest_probe": latest_probe,
        },
    )


def audit_signal_tables(conn: sqlite3.Connection) -> Check:
    manual_events = _count(conn, "SELECT COUNT(*) FROM manual_events") if _table_exists(conn, "manual_events") else 0
    news_signals = _count(conn, "SELECT COUNT(*) FROM news_signals") if _table_exists(conn, "news_signals") else 0
    news_articles = _count(conn, "SELECT COUNT(*) FROM news_articles") if _table_exists(conn, "news_articles") else 0

    if manual_events == 0 and news_signals == 0:
        status = STATUS_WARN
        message = "manual_events and news_signals are empty; intelligence signal coverage is sparse"
    else:
        status = STATUS_OK
        message = "manual/news signal tables have at least one usable source"

    return Check(
        name="intelligence_signal_coverage",
        status=status,
        message=message,
        metrics={
            "manual_events": manual_events,
            "news_signals": news_signals,
            "news_articles": news_articles,
        },
    )


def build_report(
    conn: sqlite3.Connection,
    *,
    db_path: str,
    injuries_path: Path,
    min_xg_coverage: int | None = None,
) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    checks = [
        audit_real_xg(conn, min_xg_coverage=min_xg_coverage),
        audit_market_odds(conn),
        audit_pre_match_provenance(conn),
        audit_injury_provenance(injuries_path),
        audit_lineup_provenance(conn),
        audit_signal_tables(conn),
    ]
    status_counts = {
        STATUS_OK: sum(1 for check in checks if check.status == STATUS_OK),
        STATUS_WARN: sum(1 for check in checks if check.status == STATUS_WARN),
        STATUS_CRITICAL: sum(1 for check in checks if check.status == STATUS_CRITICAL),
    }
    overall_status = "fail" if status_counts[STATUS_CRITICAL] else "pass"
    return {
        "schema_version": "v1",
        "audit": "data_provenance",
        "db_path": db_path,
        "injuries_path": str(injuries_path),
        "overall_status": overall_status,
        "status_counts": status_counts,
        "checks": [asdict(check) for check in checks],
    }


def _print_report(report: dict[str, Any]) -> None:
    print("=" * 72)
    print("AUDIT: Data Provenance and Coverage")
    print("=" * 72)
    print(f"Database: {report['db_path']}")
    print(f"Injuries: {report['injuries_path']}")
    print(f"Overall:  {report['overall_status'].upper()}")
    print()

    for check in report["checks"]:
        print(f"[{check['status'].upper():8}] {check['name']}")
        print(f"  {check['message']}")
        for key, value in check["metrics"].items():
            if key == "by_competition" and value:
                print("  by_competition:")
                for item in value[:10]:
                    print(f"    - {item['competition']}: {item['real_xg']}/{item['total']}")
                continue
            if isinstance(value, dict):
                print(f"  {key}:")
                for nested_key, nested_value in value.items():
                    print(f"    {nested_key}: {nested_value}")
            else:
                print(f"  {key}: {value}")
        print()

    counts = report["status_counts"]
    print("Summary:")
    print(f"  OK:       {counts[STATUS_OK]}")
    print(f"  WARN:     {counts[STATUS_WARN]}")
    print(f"  CRITICAL: {counts[STATUS_CRITICAL]}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit V3.6 data provenance and coverage.")
    parser.add_argument("--db", default=str(DB_PATH), help="SQLite database path.")
    parser.add_argument("--injuries", default=str(INJURIES_PATH), help="injuries.json path.")
    parser.add_argument(
        "--min-xg-coverage",
        type=int,
        default=None,
        help="Minimum rows with real xG. Defaults to max(100, 10%% of match_results).",
    )
    parser.add_argument("--json-out", default="", help="Optional JSON report path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    db_path = Path(args.db)
    injuries_path = Path(args.injuries)
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        report = build_report(
            conn,
            db_path=str(db_path),
            injuries_path=injuries_path,
            min_xg_coverage=args.min_xg_coverage,
        )
    finally:
        conn.close()

    _print_report(report)
    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON report written: {out_path}")

    return 2 if report["overall_status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())

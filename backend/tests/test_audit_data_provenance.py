from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.services.closed_loop_resolution import (
    STATUS_UNRESOLVABLE_LEGACY,
    ResolutionRecord,
    ensure_resolution_ledger,
    upsert_resolution,
)
from scripts.audit_data_provenance import (
    STATUS_CRITICAL,
    STATUS_OK,
    STATUS_WARN,
    audit_market_odds,
    build_report,
)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _write_injuries(tmp_path: Path, records: list[dict] | None = None) -> Path:
    injuries = tmp_path / "injuries.json"
    injuries.write_text(json.dumps({"injuries": records or []}), encoding="utf-8")
    return injuries


def _create_core_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE matches (
            id TEXT PRIMARY KEY,
            competition TEXT
        );
        CREATE TABLE match_results (
            match_id TEXT,
            home_goals INTEGER,
            away_goals INTEGER,
            home_xg REAL,
            away_xg REAL
        );
        CREATE TABLE market_odds (
            id TEXT PRIMARY KEY,
            match_id TEXT,
            provider TEXT,
            fetched_at TEXT
        );
        CREATE TABLE pre_match_snapshots (
            id TEXT PRIMARY KEY,
            weather_available INTEGER DEFAULT 0,
            odds_available INTEGER DEFAULT 0,
            lineup_available INTEGER DEFAULT 0,
            injury_data_available INTEGER DEFAULT 0,
            news_signals_available INTEGER DEFAULT 0,
            weather_snapshot TEXT,
            odds_snapshot TEXT,
            lineup_snapshot TEXT,
            injury_records TEXT,
            news_signal_ids TEXT,
            source_timestamps TEXT,
            odds_snapshot_id TEXT,
            weather_snapshot_id TEXT,
            injury_snapshot_id TEXT
        );
        CREATE TABLE manual_events (id TEXT PRIMARY KEY);
        CREATE TABLE news_signals (id TEXT PRIMARY KEY);
        CREATE TABLE news_articles (id TEXT PRIMARY KEY);
        CREATE TABLE lineup_probe_logs (
            id TEXT PRIMARY KEY,
            has_lineup INTEGER,
            probed_at TEXT
        );
        """
    )


def _insert_xg_rows(conn: sqlite3.Connection, *, real: int, fallback: int = 0) -> None:
    for i in range(real):
        match_id = f"match-real-{i}"
        conn.execute("INSERT INTO matches VALUES (?, ?)", (match_id, "FIFA World Cup"))
        conn.execute(
            "INSERT INTO match_results VALUES (?, 1, 0, 1.2, 0.8)",
            (match_id,),
        )
    for i in range(fallback):
        match_id = f"match-fallback-{i}"
        conn.execute("INSERT INTO matches VALUES (?, ?)", (match_id, "FIFA World Cup"))
        conn.execute(
            "INSERT INTO match_results VALUES (?, 1, 0, NULL, NULL)",
            (match_id,),
        )


def _check(report: dict, name: str) -> dict:
    return next(check for check in report["checks"] if check["name"] == name)


def test_data_provenance_marks_low_real_xg_as_critical(tmp_path):
    conn = _connect()
    _create_core_tables(conn)
    _insert_xg_rows(conn, real=0, fallback=3)

    report = build_report(
        conn,
        db_path=":memory:",
        injuries_path=_write_injuries(tmp_path),
        min_xg_coverage=1,
    )

    xg = _check(report, "real_xg_coverage")
    assert report["overall_status"] == "fail"
    assert xg["status"] == STATUS_CRITICAL
    assert xg["metrics"]["real_xg"] == 0


def test_market_odds_active_unlinked_rows_are_critical(tmp_path):
    conn = _connect()
    _create_core_tables(conn)
    _insert_xg_rows(conn, real=2)
    conn.execute(
        "INSERT INTO market_odds VALUES (?, NULL, ?, ?)",
        ("odds-1", "The Odds API", "2026-06-01T00:00:00Z"),
    )

    report = build_report(
        conn,
        db_path=":memory:",
        injuries_path=_write_injuries(tmp_path),
        min_xg_coverage=1,
    )

    market = _check(report, "market_odds_provenance")
    assert report["overall_status"] == "fail"
    assert market["status"] == STATUS_CRITICAL
    assert market["metrics"]["active_unlinked"] == 1


def test_market_odds_quarantined_unlinked_rows_do_not_fail(tmp_path):
    conn = _connect()
    _create_core_tables(conn)
    _insert_xg_rows(conn, real=2)
    ensure_resolution_ledger(conn)
    conn.execute(
        "INSERT INTO market_odds VALUES (?, NULL, ?, ?)",
        ("odds-legacy", "The Odds API", "2026-06-01T00:00:00Z"),
    )
    upsert_resolution(
        conn,
        ResolutionRecord(
            entity_table="market_odds",
            entity_id="odds-legacy",
            status=STATUS_UNRESOLVABLE_LEGACY,
            reason="legacy odds missing team/time context",
        ),
    )

    market = audit_market_odds(conn)

    assert market.status == STATUS_WARN
    assert market.metrics["active_unlinked"] == 0
    assert market.metrics["quarantined_unlinked"] == 1


def test_pre_match_available_flag_without_source_timestamps_is_warning(tmp_path):
    conn = _connect()
    _create_core_tables(conn)
    _insert_xg_rows(conn, real=2)
    conn.executemany(
        "INSERT INTO market_odds VALUES (?, ?, ?, ?)",
        [
            ("odds-1", "match-real-0", "The Odds API", "2026-06-01T00:00:00Z"),
            ("odds-2", "match-real-1", "The Odds API", "2026-06-01T00:00:00Z"),
        ],
    )
    conn.execute(
        """
        INSERT INTO pre_match_snapshots (
            id, odds_available, odds_snapshot, source_timestamps
        ) VALUES (?, 1, ?, NULL)
        """,
        ("snap-1", json.dumps({"home": 0.4, "draw": 0.3, "away": 0.3})),
    )

    report = build_report(
        conn,
        db_path=":memory:",
        injuries_path=_write_injuries(tmp_path),
        min_xg_coverage=1,
    )

    provenance = _check(report, "pre_match_snapshot_provenance")
    assert report["overall_status"] == "pass"
    assert provenance["status"] == STATUS_WARN
    assert provenance["metrics"]["missing_provenance_rows"] == 1


def test_minimal_traceable_dataset_passes_without_critical_issues(tmp_path):
    conn = _connect()
    _create_core_tables(conn)
    _insert_xg_rows(conn, real=2)
    conn.executemany(
        "INSERT INTO market_odds VALUES (?, ?, ?, ?)",
        [
            ("odds-1", "match-real-0", "The Odds API", "2026-06-01T00:00:00Z"),
            ("odds-2", "match-real-1", "The Odds API", "2026-06-01T00:00:00Z"),
        ],
    )
    conn.execute(
        """
        INSERT INTO pre_match_snapshots (
            id, odds_available, odds_snapshot, source_timestamps, odds_snapshot_id
        ) VALUES (?, 1, ?, ?, ?)
        """,
        (
            "snap-1",
            json.dumps({"home": 0.4, "draw": 0.3, "away": 0.3}),
            json.dumps({"odds": "2026-06-01T00:00:00Z"}),
            "odds-1",
        ),
    )
    conn.execute("INSERT INTO manual_events VALUES ('event-1')")
    injuries = _write_injuries(
        tmp_path,
        [
            {
                "player": "Example Player",
                "team": "Example Team",
                "status": "doubtful",
                "source": "manual",
                "last_updated": "2026-06-01T00:00:00Z",
            }
        ],
    )

    report = build_report(
        conn,
        db_path=":memory:",
        injuries_path=injuries,
        min_xg_coverage=1,
    )

    assert report["overall_status"] == "pass"
    assert _check(report, "real_xg_coverage")["status"] == STATUS_OK
    assert _check(report, "market_odds_provenance")["status"] == STATUS_OK

from __future__ import annotations

import sqlite3

from scripts.backfill_match_ids import main


def _make_match_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE teams (id TEXT PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE matches (
            id TEXT PRIMARY KEY,
            home_team_id TEXT NOT NULL,
            away_team_id TEXT NOT NULL,
            match_date TEXT NOT NULL,
            competition TEXT NOT NULL,
            stage TEXT
        );
        INSERT INTO teams (id, name) VALUES ('h1', 'Argentina'), ('a1', 'Brazil');
        INSERT INTO matches (id, home_team_id, away_team_id, match_date, competition, stage)
            VALUES ('11111111111111111111111111111111', 'h1', 'a1', '2026-06-14T14:00:00', 'FIFA World Cup 2026', 'Group Stage');
        """
    )
    return conn


def test_backfill_prediction_snapshot_updates_match_id_and_ledger(tmp_path):
    db = tmp_path / "backfill.db"
    conn = _make_match_db(db)
    conn.executescript(
        """
        CREATE TABLE prediction_snapshots (
            id TEXT PRIMARY KEY,
            match_id TEXT,
            home_team TEXT,
            away_team TEXT,
            competition TEXT,
            match_time TEXT
        );
        INSERT INTO prediction_snapshots
            VALUES ('snap1', '', 'Argentina', 'Brazil', 'FIFA World Cup 2026', '2026-06-14T14:30:00');
        """
    )
    conn.commit()
    conn.close()

    rc = main(["--db", str(db), "--table", "prediction_snapshots", "--apply", "--report-dir", str(tmp_path / "reports")])

    assert rc == 0
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    snap = conn.execute("SELECT match_id FROM prediction_snapshots WHERE id = 'snap1'").fetchone()
    ledger = conn.execute(
        "SELECT status, resolved_match_id FROM closed_loop_resolution_ledger WHERE entity_table = 'prediction_snapshots'"
    ).fetchone()
    assert snap["match_id"] == "11111111111111111111111111111111"
    assert ledger["status"] == "resolved"
    assert ledger["resolved_match_id"] == "11111111111111111111111111111111"
    conn.close()


def test_backfill_market_odds_quarantines_contextless_legacy_rows(tmp_path):
    db = tmp_path / "market.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE market_odds (
            id TEXT PRIMARY KEY,
            match_id TEXT,
            fetched_at TEXT,
            provider TEXT,
            home_implied_prob REAL,
            draw_implied_prob REAL,
            away_implied_prob REAL
        );
        INSERT INTO market_odds VALUES ('odds1', NULL, '2026-06-01T00:00:00', 'The Odds API', 0.4, 0.3, 0.3);
        """
    )
    conn.commit()
    conn.close()

    rc = main(["--db", str(db), "--table", "market_odds", "--apply", "--report-dir", str(tmp_path / "reports")])

    assert rc == 0
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    ledger = conn.execute(
        "SELECT status, reason FROM closed_loop_resolution_ledger WHERE entity_table = 'market_odds'"
    ).fetchone()
    assert ledger["status"] == "unresolvable_legacy"
    assert ledger["reason"] == "legacy_market_odds_missing_team_time_context"
    conn.close()


def test_backfill_learning_log_marks_multiple_prediction_runs_ambiguous(tmp_path):
    db = tmp_path / "learning.db"
    conn = _make_match_db(db)
    conn.executescript(
        """
        CREATE TABLE prediction_snapshots (
            id TEXT PRIMARY KEY,
            match_id TEXT,
            home_team TEXT,
            away_team TEXT,
            competition TEXT,
            match_time TEXT
        );
        CREATE TABLE prediction_runs (
            id TEXT PRIMARY KEY,
            match_id TEXT,
            run_type TEXT,
            model_version TEXT,
            as_of_time TEXT,
            created_at TEXT
        );
        CREATE TABLE prediction_learning_log (
            id TEXT PRIMARY KEY,
            match_id TEXT,
            prediction_run_id TEXT,
            snapshot_id TEXT,
            created_at TEXT,
            updated_at TEXT,
            status TEXT
        );
        INSERT INTO prediction_snapshots
            VALUES ('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', '11111111111111111111111111111111', 'Argentina', 'Brazil', 'FIFA World Cup 2026', '2026-06-14T14:30:00');
        INSERT INTO prediction_runs
            VALUES ('bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', '11111111111111111111111111111111', 't_minus_24h', 'v1', '2026-06-13T14:00:00', '2026-06-13T14:00:00');
        INSERT INTO prediction_runs
            VALUES ('cccccccccccccccccccccccccccccccc', '11111111111111111111111111111111', 't_minus_90m', 'v1', '2026-06-14T12:30:00', '2026-06-14T12:30:00');
        INSERT INTO prediction_learning_log
            VALUES ('learn1', '', NULL, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', '2026-06-15T00:00:00', '2026-06-15T00:00:00', 'active');
        """
    )
    conn.commit()
    conn.close()

    rc = main(["--db", str(db), "--table", "prediction_learning_log", "--apply", "--report-dir", str(tmp_path / "reports")])

    assert rc == 0
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    ledger = conn.execute(
        "SELECT status, resolved_match_id FROM closed_loop_resolution_ledger WHERE entity_table = 'prediction_learning_log'"
    ).fetchone()
    assert ledger["status"] == "ambiguous"
    assert ledger["resolved_match_id"] == "11111111111111111111111111111111"
    conn.close()


def test_backfill_postmatch_eval_repairs_legacy_snapshot_prediction_run_id(tmp_path):
    db = tmp_path / "postmatch.db"
    conn = _make_match_db(db)
    conn.executescript(
        """
        CREATE TABLE prediction_snapshots (
            id TEXT PRIMARY KEY,
            match_id TEXT,
            home_team TEXT,
            away_team TEXT,
            competition TEXT,
            match_time TEXT
        );
        CREATE TABLE prediction_runs (
            id TEXT PRIMARY KEY,
            match_id TEXT,
            run_type TEXT,
            model_version TEXT,
            as_of_time TEXT,
            created_at TEXT
        );
        CREATE TABLE postmatch_eval (
            id TEXT PRIMARY KEY,
            prediction_run_id TEXT,
            actual_home_goals INTEGER,
            actual_away_goals INTEGER,
            actual_result TEXT,
            created_at TEXT
        );
        INSERT INTO prediction_snapshots
            VALUES ('2fb1cd56878144878878ee884ee09f22', '11111111111111111111111111111111', 'Argentina', 'Brazil', 'FIFA World Cup 2026', '2026-06-14T14:30:00');
        INSERT INTO prediction_runs
            VALUES ('bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', '11111111111111111111111111111111', 't_minus_24h', 'v1', '2026-06-13T14:00:00', '2026-06-13T14:00:00');
        INSERT INTO postmatch_eval
            VALUES ('eval1', 'snapshot_2fb1cd56', 1, 1, 'D', '2026-06-15T00:00:00');
        """
    )
    conn.commit()
    conn.close()

    rc = main(["--db", str(db), "--table", "postmatch_eval", "--apply", "--report-dir", str(tmp_path / "reports")])

    assert rc == 0
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    postmatch = conn.execute("SELECT prediction_run_id FROM postmatch_eval WHERE id = 'eval1'").fetchone()
    ledger = conn.execute(
        "SELECT status, resolved_prediction_run_id FROM closed_loop_resolution_ledger WHERE entity_table = 'postmatch_eval'"
    ).fetchone()
    assert postmatch["prediction_run_id"] == "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    assert ledger["status"] == "resolved"
    assert ledger["resolved_prediction_run_id"] == "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    conn.close()

from __future__ import annotations

import asyncio
import sqlite3

from app.services.postmatch_stats import (
    STATSBOMB_PROVIDER,
    ensure_postmatch_team_stats_table,
    extract_statsbomb_team_stats,
    upsert_postmatch_team_stats,
)
from scripts.audit_data_provenance import STATUS_OK, audit_postmatch_stats
from scripts.backfill_statsbomb_postmatch_stats import run


def _match_payload() -> dict:
    return {
        "match_id": 12345,
        "match_date": "2022-12-18",
        "last_updated": "2023-01-01T00:00:00Z",
        "home_team": {"home_team_name": "Argentina"},
        "away_team": {"away_team_name": "France"},
        "home_score": 3,
        "away_score": 3,
        "competition_stage": {"name": "Final"},
    }


def _events() -> list[dict]:
    return [
        {
            "type": {"name": "Shot"},
            "team": {"name": "Argentina"},
            "shot": {"statsbomb_xg": 0.75, "outcome": {"name": "Goal"}},
        },
        {
            "type": {"name": "Shot"},
            "team": {"name": "Argentina"},
            "shot": {"statsbomb_xg": 0.10, "outcome": {"name": "Off T"}},
        },
        {
            "type": {"name": "Shot"},
            "team": {"name": "France"},
            "shot": {"statsbomb_xg": 0.50, "outcome": {"name": "Saved"}},
        },
        {
            "type": {"name": "Pass"},
            "team": {"name": "Argentina"},
            "pass": {"type": {"name": "Corner"}},
        },
        {
            "type": {"name": "Foul Committed"},
            "team": {"name": "Argentina"},
            "foul_committed": {"card": {"name": "Yellow Card"}},
        },
        {
            "type": {"name": "Bad Behaviour"},
            "team": {"name": "France"},
            "bad_behaviour": {"card": {"name": "Red Card"}},
        },
        {
            "type": {"name": "Foul Committed"},
            "team": {"name": "France"},
            "foul_committed": {"card": {"name": "Second Yellow"}},
        },
    ]


def test_extract_statsbomb_team_stats_counts_real_event_metrics():
    record = extract_statsbomb_team_stats(
        _match_payload(),
        _events(),
        match_id="match-1",
        available_at="2026-06-13T00:00:00Z",
        captured_at="2026-06-13T00:00:01Z",
    )

    assert record.provider == STATSBOMB_PROVIDER
    assert record.source_time == "2023-01-01T00:00:00Z"
    assert record.home_xg == 0.85
    assert record.away_xg == 0.5
    assert record.home_shots == 2
    assert record.away_shots == 1
    assert record.home_shots_on_target == 1
    assert record.away_shots_on_target == 1
    assert record.home_yellow_cards == 1
    assert record.away_red_cards == 2
    assert record.home_corners == 1
    assert record.home_possession is None


def test_upsert_postmatch_stats_writes_table_and_syncs_match_result_xg():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE match_results (
            id TEXT PRIMARY KEY,
            match_id TEXT,
            home_goals INTEGER,
            away_goals INTEGER,
            home_xg REAL,
            away_xg REAL
        )
        """
    )
    conn.execute("INSERT INTO match_results VALUES ('mr1', 'match-1', 3, 3, NULL, NULL)")
    ensure_postmatch_team_stats_table(conn)
    record = extract_statsbomb_team_stats(
        _match_payload(),
        _events(),
        match_id="match-1",
        available_at="2026-06-13T00:00:00Z",
        captured_at="2026-06-13T00:00:01Z",
    )

    upsert_postmatch_team_stats(conn, record)
    upsert_postmatch_team_stats(conn, record)

    assert conn.execute("SELECT COUNT(*) FROM postmatch_team_stats").fetchone()[0] == 1
    row = conn.execute("SELECT home_xg, away_xg FROM match_results WHERE match_id = 'match-1'").fetchone()
    assert row["home_xg"] == 0.85
    assert row["away_xg"] == 0.5
    audit = audit_postmatch_stats(conn)
    assert audit.status == STATUS_OK
    assert audit.metrics["rows_with_shots"] == 1


class FakeStatsBombService:
    async def load_competitions(self):
        return [
            {
                "competition_id": 43,
                "season_id": 106,
                "competition_name": "FIFA World Cup",
                "competition_gender": "male",
                "season_name": "2022",
            }
        ]

    async def load_matches(self, competition_id, season_id):
        return [_match_payload()]

    async def load_events(self, match_id):
        return _events()


def _make_backfill_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE teams (
            id TEXT PRIMARY KEY,
            name TEXT
        );
        CREATE TABLE matches (
            id TEXT PRIMARY KEY,
            external_id TEXT,
            home_team_id TEXT,
            away_team_id TEXT,
            match_date TEXT,
            competition TEXT
        );
        CREATE TABLE match_results (
            id TEXT PRIMARY KEY,
            match_id TEXT,
            home_goals INTEGER,
            away_goals INTEGER,
            home_xg REAL,
            away_xg REAL
        );
        INSERT INTO teams VALUES ('team-home', 'Argentina');
        INSERT INTO teams VALUES ('team-away', 'France');
        INSERT INTO matches VALUES (
            'match-1', 'statsbomb:12345', 'team-home', 'team-away',
            '2022-12-18T15:00:00', 'FIFA World Cup'
        );
        INSERT INTO match_results VALUES ('mr1', 'match-1', 3, 3, NULL, NULL);
        """
    )
    return conn


def test_statsbomb_backfill_dry_run_matches_without_writing():
    conn = _make_backfill_db()

    summary = asyncio.run(
        run(
            conn,
            seasons={"2022"},
            apply=False,
            service=FakeStatsBombService(),
            available_at="2026-06-13T00:00:00Z",
        )
    )

    assert summary.statsbomb_matches_seen == 1
    assert summary.matched_internal_matches == 1
    assert summary.stats_records_ready == 1
    assert summary.stats_records_written == 0
    assert summary.match_results_xg_would_update == 1
    assert not conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'postmatch_team_stats'"
    ).fetchone()[0]


def test_statsbomb_backfill_apply_writes_stats_and_updates_xg():
    conn = _make_backfill_db()

    summary = asyncio.run(
        run(
            conn,
            seasons={"2022"},
            apply=True,
            service=FakeStatsBombService(),
            available_at="2026-06-13T00:00:00Z",
        )
    )

    assert summary.stats_records_written == 1
    assert summary.match_results_xg_updated == 1
    assert conn.execute("SELECT COUNT(*) FROM postmatch_team_stats").fetchone()[0] == 1
    row = conn.execute("SELECT home_xg, away_xg FROM match_results WHERE match_id = 'match-1'").fetchone()
    assert row["home_xg"] == 0.85
    assert row["away_xg"] == 0.5

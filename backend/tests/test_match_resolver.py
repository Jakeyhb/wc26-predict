from __future__ import annotations

import sqlite3

from app.services.match_resolver import normalize_name, resolve_match_id


def _make_db(path):
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
        INSERT INTO teams (id, name) VALUES
            ('h1', 'Argentina'),
            ('a1', 'Brazil'),
            ('h2', 'France'),
            ('a2', 'Ivory Coast');
        INSERT INTO matches (id, home_team_id, away_team_id, match_date, competition, stage)
            VALUES ('11111111111111111111111111111111', 'h1', 'a1', '2026-06-14T14:00:00', 'FIFA World Cup 2026', 'Group J - Matchday 1');
        INSERT INTO matches (id, home_team_id, away_team_id, match_date, competition, stage)
            VALUES ('22222222222222222222222222222222', 'h2', 'a2', '2026-06-09T12:00:00', 'International Friendly', 'Friendly');
        """
    )
    conn.commit()
    conn.close()


def test_normalize_name_handles_common_aliases():
    assert normalize_name("USA") == "united states"
    assert normalize_name("Arsenal FC") == "arsenal"


def test_resolve_match_id_with_time(tmp_path):
    db = tmp_path / "test.db"
    _make_db(db)

    resolved = resolve_match_id(
        home_team="Argentina",
        away_team="Brazil",
        competition="FIFA World Cup 2026",
        kickoff_at="2026-06-14T14:30:00",
        db_path=db,
    )

    assert resolved is not None
    assert resolved.match_id == "11111111111111111111111111111111"


def test_resolve_match_id_without_time_when_unique(tmp_path):
    db = tmp_path / "test.db"
    _make_db(db)

    resolved = resolve_match_id(
        home_team="France",
        away_team="Ivory Coast",
        competition="International Friendly",
        db_path=db,
    )

    assert resolved is not None
    assert resolved.match_id == "22222222222222222222222222222222"


def test_resolve_match_id_without_time_rejects_ambiguous_pair(tmp_path):
    db = tmp_path / "test.db"
    _make_db(db)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO matches (id, home_team_id, away_team_id, match_date, competition, stage) VALUES (?, ?, ?, ?, ?, ?)",
        ("33333333333333333333333333333333", "h1", "a1", "2026-06-20T14:00:00", "FIFA World Cup 2026", "Final"),
    )
    conn.commit()
    conn.close()

    resolved = resolve_match_id(
        home_team="Argentina",
        away_team="Brazil",
        competition="FIFA World Cup 2026",
        db_path=db,
    )

    assert resolved is None

"""Create WC26 tournament data structure tables.

Creates the following tables for the 2026 FIFA World Cup:
  - wc26_groups:           48 team slots across 12 groups (A-L)
  - wc26_schedule:         All 104 matches (72 group + 32 knockout)
  - wc26_group_standings:  Live standings that update as matches complete
  - wc26_knockout_paths:   Bracket advancement links between rounds
  - wc26_third_place_ranking: Tracks the 8 best 3rd-place teams

Idempotent -- uses IF NOT EXISTS on all tables and indexes.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BACKEND_DIR / "data" / "local_stage2.db"

# ── DDL statements ──────────────────────────────────────────────────────

CREATE_GROUPS = """
CREATE TABLE IF NOT EXISTS wc26_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_name CHAR(2) NOT NULL,
    slot INTEGER NOT NULL CHECK(slot BETWEEN 1 AND 4),
    team_name VARCHAR(100),
    team_code VARCHAR(3),
    fifa_rank INTEGER,
    qualification_status VARCHAR(20) DEFAULT 'TBD',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(group_name, slot)
);
"""

CREATE_SCHEDULE = """
CREATE TABLE IF NOT EXISTS wc26_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_number INTEGER NOT NULL UNIQUE,
    home_slot VARCHAR(20) NOT NULL,
    away_slot VARCHAR(20) NOT NULL,
    stage VARCHAR(30) NOT NULL,
    group_name CHAR(2),
    match_date DATE,
    kickoff_time TIME,
    venue VARCHAR(100),
    city VARCHAR(100),
    home_team VARCHAR(100),
    away_team VARCHAR(100),
    home_goals INTEGER,
    away_goals INTEGER,
    match_status VARCHAR(20) DEFAULT 'SCHEDULED',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_STANDINGS = """
CREATE TABLE IF NOT EXISTS wc26_group_standings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_name CHAR(2) NOT NULL,
    team_slot VARCHAR(3) NOT NULL,
    team_name VARCHAR(100),
    played INTEGER DEFAULT 0,
    won INTEGER DEFAULT 0,
    drawn INTEGER DEFAULT 0,
    lost INTEGER DEFAULT 0,
    goals_for INTEGER DEFAULT 0,
    goals_against INTEGER DEFAULT 0,
    goal_diff INTEGER DEFAULT 0,
    points INTEGER DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(group_name, team_slot)
);
"""

CREATE_KNOCKOUT_PATHS = """
CREATE TABLE IF NOT EXISTS wc26_knockout_paths (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round VARCHAR(30) NOT NULL,
    match_number INTEGER NOT NULL,
    winner_advances_to_match INTEGER,
    loser_advances_to_match INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_THIRD_PLACE = """
CREATE TABLE IF NOT EXISTS wc26_third_place_ranking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_name CHAR(2) NOT NULL,
    team_slot VARCHAR(3),
    team_name VARCHAR(100),
    played INTEGER DEFAULT 0,
    points INTEGER DEFAULT 0,
    goal_diff INTEGER DEFAULT 0,
    goals_for INTEGER DEFAULT 0,
    advances BOOLEAN DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_wc26_schedule_stage ON wc26_schedule(stage);",
    "CREATE INDEX IF NOT EXISTS idx_wc26_schedule_date ON wc26_schedule(match_date);",
    "CREATE INDEX IF NOT EXISTS idx_wc26_standings_group ON wc26_group_standings(group_name);",
]

ALL_DDL = [
    CREATE_GROUPS,
    CREATE_SCHEDULE,
    CREATE_STANDINGS,
    CREATE_KNOCKOUT_PATHS,
    CREATE_THIRD_PLACE,
    *CREATE_INDEXES,
]


def create_tables(drop_first: bool = False) -> None:
    """Execute all DDL against the SQLite database.

    Args:
        drop_first: If True, drop any existing wc26_* tables first.
    """
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    if drop_first:
        for table in (
            "wc26_third_place_ranking",
            "wc26_knockout_paths",
            "wc26_group_standings",
            "wc26_schedule",
            "wc26_groups",
        ):
            cursor.execute(f"DROP TABLE IF EXISTS {table};")
            print(f"  Dropped table {table}")

    for ddl in ALL_DDL:
        cursor.execute(ddl)

    conn.commit()

    # Verify
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'wc26_%' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()

    print(f"\nCreated {len(tables)} tables: {', '.join(tables)}")


def main() -> None:
    print("Creating WC26 tournament tables...")
    print(f"Database: {DB_PATH}")
    create_tables(drop_first=False)


if __name__ == "__main__":
    main()

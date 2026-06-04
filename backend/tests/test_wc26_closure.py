"""Tests for WC26 data integrity.

Verifies that the WC26 tournament tables in the SQLite database contain
the expected number of rows and structural properties:

  - wc26_schedule has exactly 104 matches (72 group + 32 knockout)
  - Group stage has exactly 72 matches
  - wc26_groups has exactly 12 groups (A-L)
  - Each group has exactly 4 slots
  - wc26_third_place_ranking has exactly 12 entries
  - wc26_knockout_paths has data (advancement links)
  - Every team in wc26_groups has a corresponding schedule slot

Usage:
    pytest backend/tests/test_wc26_closure.py -v
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BACKEND_DIR / "data" / "local_stage2.db"

GROUPS = list("ABCDEFGHIJKL")
EXPECTED_TOTAL_MATCHES = 104
EXPECTED_GROUP_MATCHES = 72
EXPECTED_GROUPS = 12
EXPECTED_SLOTS_PER_GROUP = 4
EXPECTED_THIRD_PLACE_ENTRIES = 12


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def db() -> sqlite3.Connection:
    """Provide a connection to the WC26 local database."""
    if not DB_PATH.exists():
        pytest.fail(f"Database not found at {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def table_counts(db: sqlite3.Connection) -> dict[str, int]:
    """Return row counts for all wc26_* tables."""
    cursor = db.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name LIKE 'wc26_%' "
        "ORDER BY name"
    )
    tables = [row["name"] for row in cursor.fetchall()]
    counts: dict[str, int] = {}
    for table in tables:
        cursor = db.execute(f"SELECT COUNT(*) AS cnt FROM {table}")
        counts[table] = cursor.fetchone()["cnt"]
    return counts


# ── Schedule tests ────────────────────────────────────────────────────


class TestSchedule:
    """Tests targeting the wc26_schedule table."""

    def test_wc26_schedule_has_104_matches(self, table_counts: dict[str, int]) -> None:
        """Verify wc26_schedule has exactly 104 rows (72 group + 32 knockout)."""
        count = table_counts.get("wc26_schedule", 0)
        assert count == EXPECTED_TOTAL_MATCHES, (
            f"Expected {EXPECTED_TOTAL_MATCHES} matches in wc26_schedule, "
            f"got {count}"
        )

    def test_group_stage_has_72_matches(self, db: sqlite3.Connection) -> None:
        """Verify exactly 72 matches have stage='Group Stage'."""
        cursor = db.execute(
            "SELECT COUNT(*) AS cnt FROM wc26_schedule WHERE stage = ?",
            ("Group Stage",),
        )
        count = cursor.fetchone()["cnt"]
        assert count == EXPECTED_GROUP_MATCHES, (
            f"Expected {EXPECTED_GROUP_MATCHES} group-stage matches, "
            f"got {count}"
        )

    def test_knockout_stage_has_32_matches(self, db: sqlite3.Connection) -> None:
        """Verify exactly 32 knockout matches (non-Group Stage)."""
        cursor = db.execute(
            "SELECT COUNT(*) AS cnt FROM wc26_schedule WHERE stage != ?",
            ("Group Stage",),
        )
        count = cursor.fetchone()["cnt"]
        assert count == EXPECTED_TOTAL_MATCHES - EXPECTED_GROUP_MATCHES, (
            f"Expected 32 knockout matches, got {count}"
        )

    def test_all_match_numbers_are_unique(self, db: sqlite3.Connection) -> None:
        """Verify no duplicate match_number values."""
        cursor = db.execute(
            "SELECT COUNT(*) AS cnt FROM ("
            "  SELECT match_number FROM wc26_schedule "
            "  GROUP BY match_number HAVING COUNT(*) > 1"
            ")"
        )
        dupes = cursor.fetchone()["cnt"]
        assert dupes == 0, f"Found {dupes} duplicate match_number(s)"

    def test_match_numbers_are_one_to_104(self, db: sqlite3.Connection) -> None:
        """Verify match_number values span 1..104 without gaps."""
        cursor = db.execute(
            "SELECT COUNT(*) AS cnt, MIN(match_number) AS mn, "
            "MAX(match_number) AS mx FROM wc26_schedule"
        )
        row = cursor.fetchone()
        assert row["cnt"] == 104, f"Expected 104 rows, got {row['cnt']}"
        assert row["mn"] == 1, f"Min match_number is {row['mn']}, expected 1"
        assert row["mx"] == 104, f"Max match_number is {row['mx']}, expected 104"


# ── Groups tests ──────────────────────────────────────────────────────


class TestGroups:
    """Tests targeting the wc26_groups table."""

    def test_wc26_groups_has_12_groups(self, db: sqlite3.Connection) -> None:
        """Verify exactly 12 distinct group names (A through L)."""
        cursor = db.execute(
            "SELECT DISTINCT group_name FROM wc26_groups ORDER BY group_name"
        )
        groups = [row["group_name"] for row in cursor.fetchall()]
        assert groups == GROUPS, (
            f"Expected groups {GROUPS}, got {groups}"
        )

    def test_each_group_has_4_slots(self, db: sqlite3.Connection) -> None:
        """Verify each of the 12 groups has exactly 4 slot entries."""
        cursor = db.execute(
            "SELECT group_name, COUNT(*) AS cnt "
            "FROM wc26_groups GROUP BY group_name ORDER BY group_name"
        )
        rows = cursor.fetchall()
        assert len(rows) == EXPECTED_GROUPS, (
            f"Expected {EXPECTED_GROUPS} group rows, got {len(rows)}"
        )
        for row in rows:
            assert row["cnt"] == EXPECTED_SLOTS_PER_GROUP, (
                f"Group {row['group_name']} has {row['cnt']} slots, "
                f"expected {EXPECTED_SLOTS_PER_GROUP}"
            )

    def test_slots_are_one_to_four(self, db: sqlite3.Connection) -> None:
        """Verify slot values are 1, 2, 3, 4 within each group."""
        cursor = db.execute(
            "SELECT group_name, slot FROM wc26_groups ORDER BY group_name, slot"
        )
        rows = cursor.fetchall()
        by_group: dict[str, list[int]] = {}
        for row in rows:
            by_group.setdefault(row["group_name"], []).append(row["slot"])
        for group, slots in by_group.items():
            assert slots == [1, 2, 3, 4], (
                f"Group {group} has slots {slots}, expected [1, 2, 3, 4]"
            )

    def test_total_groups_slots(self, table_counts: dict[str, int]) -> None:
        """Verify 48 total group slots."""
        count = table_counts.get("wc26_groups", 0)
        assert count == 48, f"Expected 48 group slots, got {count}"


# ── Knockout paths tests ──────────────────────────────────────────────


class TestKnockoutPaths:
    """Tests targeting the wc26_knockout_paths table."""

    def test_knockout_paths_exist(self, table_counts: dict[str, int]) -> None:
        """Verify wc26_knockout_paths has data."""
        count = table_counts.get("wc26_knockout_paths", 0)
        assert count > 0, "wc26_knockout_paths is empty"
        assert count >= 32, (
            f"Expected at least 32 knockout path entries, got {count}"
        )

    def test_knockout_paths_have_valid_references(self, db: sqlite3.Connection) -> None:
        """Verify winner_advances_to_match references exist in wc26_schedule."""
        cursor = db.execute(
            "SELECT DISTINCT k.winner_advances_to_match "
            "FROM wc26_knockout_paths k "
            "WHERE k.winner_advances_to_match IS NOT NULL "
            "  AND k.winner_advances_to_match NOT IN "
            "    (SELECT match_number FROM wc26_schedule)"
        )
        orphans = [row["winner_advances_to_match"] for row in cursor.fetchall()]
        assert len(orphans) == 0, (
            f"winner_advances_to_match references {orphans} not found in schedule"
        )


# ── Third place ranking tests ─────────────────────────────────────────


class TestThirdPlace:
    """Tests targeting the wc26_third_place_ranking table."""

    def test_third_place_table_has_12_entries(
        self, table_counts: dict[str, int]
    ) -> None:
        """Verify wc26_third_place_ranking has 12 entries (one per group)."""
        count = table_counts.get("wc26_third_place_ranking", 0)
        assert count == EXPECTED_THIRD_PLACE_ENTRIES, (
            f"Expected {EXPECTED_THIRD_PLACE_ENTRIES} third-place entries, "
            f"got {count}"
        )

    def test_third_place_has_one_per_group(self, db: sqlite3.Connection) -> None:
        """Verify exactly one third-place entry per group."""
        cursor = db.execute(
            "SELECT group_name, COUNT(*) AS cnt "
            "FROM wc26_third_place_ranking "
            "GROUP BY group_name ORDER BY group_name"
        )
        rows = cursor.fetchall()
        assert len(rows) == EXPECTED_GROUPS, (
            f"Expected {EXPECTED_GROUPS} groups in third-place ranking, "
            f"got {len(rows)}"
        )
        for row in rows:
            assert row["cnt"] == 1, (
                f"Group {row['group_name']} has {row['cnt']} third-place entries"
            )


# ── Cross-table consistency ───────────────────────────────────────────


class TestCrossTableConsistency:
    """Tests that verify relationships between tables."""

    def test_each_team_has_schedule_slot(self, db: sqlite3.Connection) -> None:
        """Verify every team_slot in wc26_groups appears in wc26_schedule.

        Each group slot (e.g. A1, B3) must appear as either home_slot or
        away_slot in at least one group-stage match.
        """
        cursor = db.execute(
            "SELECT group_name || CAST(slot AS TEXT) AS team_slot "
            "FROM wc26_groups"
        )
        group_slots = {row["team_slot"] for row in cursor.fetchall()}

        cursor = db.execute(
            "SELECT DISTINCT home_slot AS slot FROM wc26_schedule "
            "WHERE stage = 'Group Stage' "
            "UNION "
            "SELECT DISTINCT away_slot FROM wc26_schedule "
            "WHERE stage = 'Group Stage'"
        )
        schedule_slots = {row["slot"] for row in cursor.fetchall()}

        missing = group_slots - schedule_slots
        assert len(missing) == 0, (
            f"Group slots {missing} have no corresponding schedule entries"
        )

    def test_group_standings_match_group_count(self, db: sqlite3.Connection) -> None:
        """Verify wc26_group_standings has 48 rows (12 groups x 4 slots)."""
        cursor = db.execute("SELECT COUNT(*) AS cnt FROM wc26_group_standings")
        count = cursor.fetchone()["cnt"]
        assert count == 48, (
            f"Expected 48 group standing rows, got {count}"
        )

    def test_standings_have_all_groups(self, db: sqlite3.Connection) -> None:
        """Verify wc26_group_standings covers all 12 groups."""
        cursor = db.execute(
            "SELECT DISTINCT group_name FROM wc26_group_standings "
            "ORDER BY group_name"
        )
        groups = [row["group_name"] for row in cursor.fetchall()]
        assert groups == GROUPS, (
            f"Expected standings for groups {GROUPS}, got {groups}"
        )

    def test_schedule_has_team_names_or_placeholders(self, db: sqlite3.Connection) -> None:
        """Verify all 72 group-stage matches have non-null team references.

        The home_slot / away_slot columns must be populated (team names are
        optional until the draw is complete).
        """
        cursor = db.execute(
            "SELECT COUNT(*) AS cnt FROM wc26_schedule "
            "WHERE stage = 'Group Stage' AND "
            "(home_slot IS NULL OR away_slot IS NULL)"
        )
        null_slots = cursor.fetchone()["cnt"]
        assert null_slots == 0, (
            f"Found {null_slots} group-stage matches with NULL slot references"
        )

    def test_schedule_stage_distribution(self, db: sqlite3.Connection) -> None:
        """Verify all expected knockout stages are present."""
        cursor = db.execute(
            "SELECT stage, COUNT(*) AS cnt "
            "FROM wc26_schedule "
            "WHERE stage != 'Group Stage' "
            "GROUP BY stage ORDER BY stage"
        )
        stages = {row["stage"]: row["cnt"] for row in cursor.fetchall()}
        expected = {
            "Round of 32": 16,
            "Round of 16": 8,
            "Quarter-final": 4,
            "Semi-final": 2,
            "Third Place": 1,
            "Final": 1,
        }
        assert stages == expected, (
            f"Knockout stage distribution mismatch.\n"
            f"  Got:      {stages}\n"
            f"  Expected: {expected}"
        )

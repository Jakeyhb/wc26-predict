"""test_dashboard_db.py — Read-only enforcement and DashboardDB functionality."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from dashboard.db import DashboardDB, _validate_read_only


class TestValidateReadOnly:
    """Test the SQL read-only validation regex."""

    def test_select_passes(self):
        _validate_read_only("SELECT * FROM matches")

    def test_select_with_where_passes(self):
        _validate_read_only("SELECT * FROM matches WHERE id = 1")

    def test_select_with_join_passes(self):
        _validate_read_only(
            "SELECT * FROM matches m JOIN teams t ON m.home_team_id = t.id"
        )

    def test_drop_raises(self):
        with pytest.raises(ValueError):
            _validate_read_only("DROP TABLE matches")

    def test_delete_raises(self):
        with pytest.raises(ValueError):
            _validate_read_only("DELETE FROM matches WHERE id = 1")

    def test_update_raises(self):
        with pytest.raises(ValueError):
            _validate_read_only("UPDATE matches SET status='finished'")

    def test_insert_raises(self):
        with pytest.raises(ValueError):
            _validate_read_only("INSERT INTO matches (id) VALUES (1)")

    def test_alter_raises(self):
        with pytest.raises(ValueError):
            _validate_read_only("ALTER TABLE matches ADD COLUMN foo INT")

    def test_create_raises(self):
        with pytest.raises(ValueError):
            _validate_read_only("CREATE TABLE foo (id INT)")

    def test_attach_raises(self):
        with pytest.raises(ValueError):
            _validate_read_only("ATTACH DATABASE 'foo.db' AS bar")

    def test_multi_statement_injection_raises(self):
        with pytest.raises(ValueError):
            _validate_read_only("SELECT 1;\nDROP TABLE matches --")

    def test_case_insensitive_drop_raises(self):
        with pytest.raises(ValueError):
            _validate_read_only("drop table matches")

    def test_case_insensitive_delete_raises(self):
        with pytest.raises(ValueError):
            _validate_read_only("delete from matches where id=1")

    def test_leading_whitespace_raises(self):
        with pytest.raises(ValueError):
            _validate_read_only("   DROP TABLE matches")


class TestDashboardDB:
    """Test the DashboardDB class functionality."""

    def test_db_path_exists(self):
        db = DashboardDB()
        assert db.db_path.exists(), f"DB not found at {db.db_path}"

    def test_connect_returns_connection(self):
        db = DashboardDB()
        conn = db.connect()
        assert conn is not None
        conn.close()

    def test_get_tables_returns_list(self):
        db = DashboardDB()
        tables = db.get_tables()
        assert isinstance(tables, list)
        assert len(tables) > 0
        assert "matches" in tables or "teams" in tables

    def test_get_row_count_returns_int(self):
        db = DashboardDB()
        tables = db.get_tables()
        if tables:
            count = db.get_row_count(tables[0])
            assert isinstance(count, int)
            assert count >= 0

    def test_get_table_info_returns_list(self):
        db = DashboardDB()
        tables = db.get_tables()
        if tables:
            info = db.get_table_info(tables[0])
            assert isinstance(info, list)

    def test_query_returns_rows(self):
        db = DashboardDB()
        tables = db.get_tables()
        if "teams" in tables:
            rows = db.query("SELECT name FROM teams LIMIT 5")
            assert len(rows) <= 5

    def test_write_query_raises(self):
        db = DashboardDB()
        with pytest.raises(ValueError):
            db.query("DROP TABLE matches")

    def test_get_teams_returns_sorted(self):
        db = DashboardDB()
        teams = db.get_teams()
        assert len(teams) > 0
        assert teams == sorted(teams)

    def test_get_db_stats_returns_dict(self):
        db = DashboardDB()
        stats = db.get_db_stats()
        assert isinstance(stats, dict)
        assert "matches" in stats or "teams" in stats

    def test_connect_fails_for_nonexistent_db(self):
        db = DashboardDB(db_path=Path("/nonexistent/path.db"))
        with pytest.raises(FileNotFoundError):
            db.connect()

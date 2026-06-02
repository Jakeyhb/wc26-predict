#!/usr/bin/env python3
"""Merge duplicate national team records in the teams table."""

import sqlite3, sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BACKEND_DIR / "data" / "local_stage2.db"

NAME_MAP = {
    "Korea Republic": "South Korea",
    "Czechia": "Czech Republic",
    "Curacao": "Curacao",
    "TBD": None,
}


def get_best_id(conn, team_name):
    rows = conn.execute("""
        SELECT t.id, COUNT(mr.match_id) as cnt
        FROM teams t
        LEFT JOIN matches m ON (m.home_team_id = t.id OR m.away_team_id = t.id)
        LEFT JOIN match_results mr ON mr.match_id = m.id
        WHERE t.name = ? AND t.team_type = 'national'
        GROUP BY t.id ORDER BY cnt DESC
    """, (team_name,)).fetchall()
    if not rows:
        return "", 0
    return rows[0][0], rows[0][1]


def merge(conn, dry_run):
    stats = {"merged": 0, "errors": 0}
    dupes = conn.execute("""
        SELECT name, COUNT(*) as cnt FROM teams
        WHERE team_type = 'national'
        GROUP BY name HAVING cnt > 1
    """).fetchall()

    for name, cnt in dupes:
        best_id, best_train = get_best_id(conn, name)
        if best_train == 0:
            continue

        all_ids = [r[0] for r in conn.execute(
            "SELECT id FROM teams WHERE name = ? AND team_type = 'national'", (name,)
        ).fetchall()]

        for old_id in all_ids:
            if old_id == best_id:
                continue

            refs = conn.execute("""
                SELECT
                    (SELECT COUNT(*) FROM matches WHERE home_team_id = ?1) +
                    (SELECT COUNT(*) FROM matches WHERE away_team_id = ?1),
                    (SELECT COUNT(*) FROM players WHERE team_id = ?1)
            """, (old_id,)).fetchone()

            if dry_run:
                if refs[0] > 0:
                    print(f"  [DRY] {name}: merge {old_id[:20]}... -> {best_id[:20]}... (refs={refs[0]})")
                stats["merged"] += 1
                continue

            # Update match references
            conn.execute(
                "UPDATE matches SET home_team_id = ? WHERE home_team_id = ?",
                (best_id, old_id))
            conn.execute(
                "UPDATE matches SET away_team_id = ? WHERE away_team_id = ?",
                (best_id, old_id))
            # Update player references
            conn.execute(
                "UPDATE players SET team_id = ? WHERE team_id = ?",
                (best_id, old_id))
            # Delete old orphan team record
            conn.execute("DELETE FROM teams WHERE id = ?", (old_id,))
            stats["merged"] += 1

    return stats


def fix_names(conn, dry_run):
    stats = {"fixed": 0}
    for old_name, new_name in NAME_MAP.items():
        if new_name is None:
            continue
        old_row = conn.execute(
            "SELECT id FROM teams WHERE name = ? AND team_type = 'national'",
            (old_name,)).fetchone()
        if not old_row:
            continue
        old_id = old_row[0]
        new_id, new_train = get_best_id(conn, new_name)

        if new_train == 0:
            if not dry_run:
                conn.execute("UPDATE teams SET name = ? WHERE id = ?",
                            (new_name, old_id))
            print(f"  {'[DRY] ' if dry_run else ''}Renamed: '{old_name}' -> '{new_name}'")
            stats["fixed"] += 1
            continue

        if dry_run:
            old_train = conn.execute("""
                SELECT COUNT(mr.match_id) FROM matches m
                JOIN match_results mr ON mr.match_id = m.id
                WHERE m.home_team_id = ? OR m.away_team_id = ?
            """, (old_id, old_id)).fetchone()[0]
            print(f"  [DRY] Map: '{old_name}' (train={old_train}) -> '{new_name}' (train={new_train})")
            stats["fixed"] += 1
            continue

        conn.execute("UPDATE matches SET home_team_id = ? WHERE home_team_id = ?",
                    (new_id, old_id))
        conn.execute("UPDATE matches SET away_team_id = ? WHERE away_team_id = ?",
                    (new_id, old_id))
        conn.execute("UPDATE players SET team_id = ? WHERE team_id = ?",
                    (new_id, old_id))
        conn.execute("DELETE FROM teams WHERE id = ?", (old_id,))
        print(f"  Mapped: '{old_name}' -> '{new_name}'")
        stats["fixed"] += 1
    return stats


def main():
    dry_run = "--dry-run" in sys.argv
    conn = sqlite3.connect(str(DB_PATH))

    print(f"\n--- {'DRY RUN' if dry_run else 'LIVE MERGE'} ---")

    s1 = merge(conn, dry_run)
    s2 = fix_names(conn, dry_run)

    if not dry_run:
        conn.commit()
        print("Committed.")

    dupes = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT name FROM teams WHERE team_type = 'national' GROUP BY name HAVING COUNT(*) > 1
        )
    """).fetchone()[0]

    conn.close()
    print(f"\nMerged: {s1['merged']}, Names fixed: {s2['fixed']}, Dupes remaining: {dupes}")


if __name__ == "__main__":
    main()

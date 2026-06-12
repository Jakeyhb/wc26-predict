#!/usr/bin/env python3
"""Bind WC26 group slots from matches into wc26_* helper tables.

Knockout teams are intentionally not filled because they are unknown until the
group stage completes. Default mode is dry-run; pass --apply to update SQLite.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "local_stage2.db"
GROUPS = tuple("ABCDEFGHIJKL")


def _load_slot_mapping(conn: sqlite3.Connection) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for group in GROUPS:
        rows = list(
            conn.execute(
                """
                SELECT ht.name AS home_team, at.name AS away_team, m.match_date
                FROM matches m
                JOIN teams ht ON ht.id = m.home_team_id
                JOIN teams at ON at.id = m.away_team_id
                WHERE m.competition = 'FIFA World Cup 2026'
                  AND m.stage = ?
                ORDER BY m.match_date ASC
                """,
                (f"Group {group} - Matchday 1",),
            )
        )
        if len(rows) < 2:
            continue
        mapping[f"{group}1"] = rows[0]["home_team"]
        mapping[f"{group}2"] = rows[0]["away_team"]
        mapping[f"{group}3"] = rows[1]["home_team"]
        mapping[f"{group}4"] = rows[1]["away_team"]
    return mapping


def _team_for_slot(slot: str | None, mapping: dict[str, str]) -> str | None:
    if not slot:
        return None
    return mapping.get(slot.strip().upper())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bind WC26 group slots from matches table.")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--apply", action="store_true", help="Actually update the DB. Default is dry-run.")
    args = parser.parse_args(argv)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        mapping = _load_slot_mapping(conn)
        print("=" * 72)
        print(f"WC26 GROUP SLOT BIND {'APPLY' if args.apply else 'DRY-RUN'}")
        print("=" * 72)
        print(f"Resolved slots: {len(mapping)}/48")
        for slot in sorted(mapping):
            print(f"  {slot}: {mapping[slot]}")

        schedule_updates = 0
        for row in conn.execute("SELECT id, home_slot, away_slot FROM wc26_schedule WHERE stage = 'Group Stage'"):
            home_team = _team_for_slot(row["home_slot"], mapping)
            away_team = _team_for_slot(row["away_slot"], mapping)
            if home_team and away_team:
                schedule_updates += 1
                if args.apply:
                    conn.execute(
                        "UPDATE wc26_schedule SET home_team = ?, away_team = ? WHERE id = ?",
                        (home_team, away_team, row["id"]),
                    )

        group_updates = 0
        standings_updates = 0
        for slot, team_name in mapping.items():
            match = re.fullmatch(r"([A-L])([1-4])", slot)
            if not match:
                continue
            group, slot_num = match.group(1), int(match.group(2))
            group_updates += 1
            standings_updates += 1
            if args.apply:
                conn.execute(
                    "UPDATE wc26_groups SET team_name = ?, qualification_status = 'qualified' WHERE group_name = ? AND slot = ?",
                    (team_name, group, slot_num),
                )
                conn.execute(
                    "UPDATE wc26_group_standings SET team_name = ? WHERE team_slot = ?",
                    (team_name, slot),
                )

        if args.apply:
            conn.commit()
    finally:
        conn.close()

    print("\nSummary:")
    print(f"  group slots updateable: {group_updates}/48")
    print(f"  standings updateable: {standings_updates}/48")
    print(f"  group-stage fixtures updateable: {schedule_updates}/72")
    return 0 if len(mapping) == 48 and schedule_updates == 72 else 2


if __name__ == "__main__":
    raise SystemExit(main())

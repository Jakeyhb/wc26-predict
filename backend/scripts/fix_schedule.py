#!/usr/bin/env python3
"""fix_schedule.py — WC26 schedule fix (V3.7.2)

Fixes 5 database issues:
  1. matches table — 72 group-stage match dates + incorrect pairings
  2. wc26_schedule table — group-stage dates + kickoff times
  3. matches table — 32 knockout match dates + opponent slot labels
  4. wc26_knockout_paths table — bracket path rebuild
  5. Global UTC time consistency

Data sources: FIFA Official / Tencent Sports / dongqiudi / bracketmundial2026.com
All times stored as UTC (Beijing Time - 8 hours).

Usage:
    python scripts/fix_schedule.py          # execute fixes
    python scripts/fix_schedule.py --dry-run # preview only
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "local_stage2.db"

# ============================================================================
# Fix 1+2 data: 72 group-stage matches
# ============================================================================
# Format: (match_date_UTC, home_team, away_team, stage)

GROUP_MATCHES = [
    # ===== Matchday 1 =====
    # Jun 12 BJT
    ("2026-06-11T19:00:00", "Mexico", "South Africa", "Group A - Matchday 1"),
    ("2026-06-12T02:00:00", "South Korea", "Czech Republic", "Group A - Matchday 1"),
    # Jun 13 BJT
    ("2026-06-12T19:00:00", "Canada", "Bosnia and Herzegovina", "Group B - Matchday 1"),
    ("2026-06-13T01:00:00", "United States", "Paraguay", "Group D - Matchday 1"),
    ("2026-06-13T04:00:00", "Australia", "Turkey", "Group D - Matchday 1"),
    # Jun 14 BJT
    ("2026-06-13T19:00:00", "Qatar", "Switzerland", "Group B - Matchday 1"),
    ("2026-06-13T22:00:00", "Brazil", "Morocco", "Group C - Matchday 1"),
    ("2026-06-14T01:00:00", "Haiti", "Scotland", "Group C - Matchday 1"),
    # Jun 15 BJT
    ("2026-06-14T17:00:00", "Germany", "Curacao", "Group E - Matchday 1"),
    ("2026-06-14T20:00:00", "Netherlands", "Japan", "Group F - Matchday 1"),
    ("2026-06-14T23:00:00", "Ivory Coast", "Ecuador", "Group E - Matchday 1"),
    ("2026-06-15T02:00:00", "Tunisia", "Sweden", "Group F - Matchday 1"),
    # Jun 16 BJT
    ("2026-06-15T16:00:00", "Spain", "Cape Verde", "Group H - Matchday 1"),
    ("2026-06-15T19:00:00", "Belgium", "Egypt", "Group G - Matchday 1"),
    ("2026-06-15T22:00:00", "Saudi Arabia", "Uruguay", "Group H - Matchday 1"),
    ("2026-06-16T01:00:00", "Iran", "New Zealand", "Group G - Matchday 1"),
    # Jun 17 BJT
    ("2026-06-16T19:00:00", "France", "Senegal", "Group I - Matchday 1"),
    ("2026-06-16T22:00:00", "Iraq", "Norway", "Group I - Matchday 1"),
    ("2026-06-17T01:00:00", "Argentina", "Algeria", "Group J - Matchday 1"),
    ("2026-06-17T04:00:00", "Austria", "Jordan", "Group J - Matchday 1"),
    # Jun 18 BJT
    ("2026-06-17T17:00:00", "Portugal", "DR Congo", "Group K - Matchday 1"),
    ("2026-06-17T20:00:00", "England", "Croatia", "Group L - Matchday 1"),
    ("2026-06-17T23:00:00", "Ghana", "Panama", "Group L - Matchday 1"),
    ("2026-06-18T02:00:00", "Uzbekistan", "Colombia", "Group K - Matchday 1"),

    # ===== Matchday 2 =====
    # Jun 19 BJT
    ("2026-06-18T16:00:00", "Czech Republic", "South Africa", "Group A - Matchday 2"),
    ("2026-06-18T19:00:00", "Switzerland", "Bosnia and Herzegovina", "Group B - Matchday 2"),
    ("2026-06-18T22:00:00", "Canada", "Qatar", "Group B - Matchday 2"),
    ("2026-06-19T01:00:00", "Mexico", "South Korea", "Group A - Matchday 2"),
    # Jun 20 BJT
    ("2026-06-19T19:00:00", "United States", "Australia", "Group D - Matchday 2"),
    ("2026-06-19T22:00:00", "Scotland", "Morocco", "Group C - Matchday 2"),
    ("2026-06-20T01:00:00", "Brazil", "Haiti", "Group C - Matchday 2"),
    ("2026-06-20T04:00:00", "Turkey", "Paraguay", "Group D - Matchday 2"),
    # Jun 21 BJT
    ("2026-06-20T17:00:00", "Netherlands", "Sweden", "Group F - Matchday 2"),
    ("2026-06-20T20:00:00", "Germany", "Ivory Coast", "Group E - Matchday 2"),
    ("2026-06-21T00:00:00", "Ecuador", "Curacao", "Group E - Matchday 2"),
    ("2026-06-21T04:00:00", "Tunisia", "Japan", "Group F - Matchday 2"),
    # Jun 22 BJT
    ("2026-06-21T16:00:00", "Spain", "Saudi Arabia", "Group H - Matchday 2"),
    ("2026-06-21T19:00:00", "Belgium", "Iran", "Group G - Matchday 2"),
    ("2026-06-21T22:00:00", "Uruguay", "Cape Verde", "Group H - Matchday 2"),
    ("2026-06-22T01:00:00", "New Zealand", "Egypt", "Group G - Matchday 2"),
    # Jun 23 BJT
    ("2026-06-22T17:00:00", "Argentina", "Austria", "Group J - Matchday 2"),
    ("2026-06-22T21:00:00", "France", "Iraq", "Group I - Matchday 2"),
    ("2026-06-23T00:00:00", "Norway", "Senegal", "Group I - Matchday 2"),
    ("2026-06-23T03:00:00", "Jordan", "Algeria", "Group J - Matchday 2"),
    # Jun 24 BJT
    ("2026-06-23T17:00:00", "Portugal", "Uzbekistan", "Group K - Matchday 2"),
    ("2026-06-23T20:00:00", "England", "Ghana", "Group L - Matchday 2"),
    ("2026-06-23T23:00:00", "Panama", "Croatia", "Group L - Matchday 2"),
    ("2026-06-24T02:00:00", "Colombia", "DR Congo", "Group K - Matchday 2"),

    # ===== Matchday 3 (simultaneous kickoffs per group) =====
    # Jun 25 BJT
    ("2026-06-24T19:00:00", "Switzerland", "Canada", "Group B - Matchday 3"),
    ("2026-06-24T19:00:00", "Bosnia and Herzegovina", "Qatar", "Group B - Matchday 3"),
    ("2026-06-24T22:00:00", "Scotland", "Brazil", "Group C - Matchday 3"),
    ("2026-06-24T22:00:00", "Morocco", "Haiti", "Group C - Matchday 3"),
    ("2026-06-25T01:00:00", "Czech Republic", "Mexico", "Group A - Matchday 3"),
    ("2026-06-25T01:00:00", "South Africa", "South Korea", "Group A - Matchday 3"),
    # Jun 26 BJT
    ("2026-06-25T20:00:00", "Ecuador", "Germany", "Group E - Matchday 3"),
    ("2026-06-25T20:00:00", "Curacao", "Ivory Coast", "Group E - Matchday 3"),
    ("2026-06-25T23:00:00", "Japan", "Sweden", "Group F - Matchday 3"),
    ("2026-06-25T23:00:00", "Tunisia", "Netherlands", "Group F - Matchday 3"),
    ("2026-06-26T02:00:00", "Turkey", "United States", "Group D - Matchday 3"),
    ("2026-06-26T02:00:00", "Paraguay", "Australia", "Group D - Matchday 3"),
    # Jun 27 BJT
    ("2026-06-26T19:00:00", "Norway", "France", "Group I - Matchday 3"),
    ("2026-06-26T19:00:00", "Senegal", "Iraq", "Group I - Matchday 3"),
    ("2026-06-27T00:00:00", "Cape Verde", "Saudi Arabia", "Group H - Matchday 3"),
    ("2026-06-27T00:00:00", "Uruguay", "Spain", "Group H - Matchday 3"),
    ("2026-06-27T03:00:00", "Egypt", "Iran", "Group G - Matchday 3"),
    ("2026-06-27T03:00:00", "New Zealand", "Belgium", "Group G - Matchday 3"),
    # Jun 28 BJT
    ("2026-06-27T21:00:00", "Panama", "England", "Group L - Matchday 3"),
    ("2026-06-27T21:00:00", "Croatia", "Ghana", "Group L - Matchday 3"),
    ("2026-06-27T23:30:00", "Colombia", "Portugal", "Group K - Matchday 3"),
    ("2026-06-27T23:30:00", "DR Congo", "Uzbekistan", "Group K - Matchday 3"),
    ("2026-06-28T02:00:00", "Algeria", "Austria", "Group J - Matchday 3"),
    ("2026-06-28T02:00:00", "Jordan", "Argentina", "Group J - Matchday 3"),
]

# ============================================================================
# Fix 3 data: 32 knockout matches
# ============================================================================
# Format: (match_date_UTC, stage, opponent_slot_home, opponent_slot_away)

KNOCKOUT_MATCHES = [
    # Round of 32 (M73-M88)
    ("2026-06-28T19:00:00", "Round of 32", "2nd Group A", "2nd Group B"),
    ("2026-06-28T20:30:00", "Round of 32", "1st Group E", "3rd Group A/B/C/D/F"),
    ("2026-06-29T01:00:00", "Round of 32", "1st Group F", "2nd Group C"),
    ("2026-06-29T05:00:00", "Round of 32", "1st Group C", "2nd Group F"),
    ("2026-06-29T09:00:00", "Round of 32", "1st Group I", "3rd Group C/D/F/G/H"),
    ("2026-06-30T01:00:00", "Round of 32", "2nd Group E", "2nd Group I"),
    ("2026-06-30T05:00:00", "Round of 32", "1st Group A", "3rd Group C/E/F/H/I"),
    ("2026-06-30T09:00:00", "Round of 32", "1st Group L", "3rd Group E/H/I/J/K"),
    ("2026-07-01T00:00:00", "Round of 32", "1st Group D", "3rd Group B/E/F/I/J"),
    ("2026-07-01T04:00:00", "Round of 32", "1st Group G", "3rd Group A/E/H/I/J"),
    ("2026-07-01T08:00:00", "Round of 32", "2nd Group K", "2nd Group L"),
    ("2026-07-02T03:00:00", "Round of 32", "1st Group H", "2nd Group J"),
    ("2026-07-02T07:00:00", "Round of 32", "1st Group B", "3rd Group E/F/G/I/J"),
    ("2026-07-02T11:00:00", "Round of 32", "1st Group J", "2nd Group H"),
    ("2026-07-03T02:00:00", "Round of 32", "1st Group K", "3rd Group D/E/I/J/L"),
    ("2026-07-03T06:00:00", "Round of 32", "2nd Group D", "2nd Group G"),

    # Round of 16 (M89-M96)
    ("2026-07-04T01:00:00", "Round of 16", "Winner M74", "Winner M77"),
    ("2026-07-04T05:00:00", "Round of 16", "Winner M73", "Winner M75"),
    ("2026-07-05T04:00:00", "Round of 16", "Winner M76", "Winner M78"),
    ("2026-07-05T08:00:00", "Round of 16", "Winner M79", "Winner M80"),
    ("2026-07-06T03:00:00", "Round of 16", "Winner M83", "Winner M84"),
    ("2026-07-06T08:00:00", "Round of 16", "Winner M81", "Winner M82"),
    ("2026-07-07T00:00:00", "Round of 16", "Winner M86", "Winner M88"),
    ("2026-07-07T04:00:00", "Round of 16", "Winner M85", "Winner M87"),

    # Quarterfinals (M97-M100)
    ("2026-07-09T04:00:00", "Quarterfinal", "Winner M89", "Winner M90"),
    ("2026-07-10T03:00:00", "Quarterfinal", "Winner M91", "Winner M92"),
    ("2026-07-11T05:00:00", "Quarterfinal", "Winner M93", "Winner M94"),
    ("2026-07-11T09:00:00", "Quarterfinal", "Winner M95", "Winner M96"),

    # Semifinals (M101-M102)
    ("2026-07-15T03:00:00", "Semifinal", "Winner M97", "Winner M98"),
    ("2026-07-16T03:00:00", "Semifinal", "Winner M99", "Winner M100"),

    # Third Place & Final
    ("2026-07-19T05:00:00", "Third Place Playoff", "Loser M101", "Loser M102"),
    ("2026-07-19T03:00:00", "Final", "Winner M101", "Winner M102"),
]

# ============================================================================
# Fix 4 data: correct knockout bracket paths
# ============================================================================
# Source: bracketmundial2026.com / FIFA official
# Format: (round_name, match_number, winner_advances_to, loser_advances_to)

CORRECT_KNOCKOUT_PATHS = [
    # Round of 32 -> Round of 16
    # M89 = M74 v M77, M90 = M73 v M75
    ("Round of 32", 73, 90, None),
    ("Round of 32", 74, 89, None),
    ("Round of 32", 75, 90, None),
    # M91 = M76 v M78
    ("Round of 32", 76, 91, None),
    ("Round of 32", 77, 89, None),
    ("Round of 32", 78, 91, None),
    # M92 = M79 v M80
    ("Round of 32", 79, 92, None),
    ("Round of 32", 80, 92, None),
    # M93 = M83 v M84, M94 = M81 v M82
    ("Round of 32", 81, 94, None),
    ("Round of 32", 82, 94, None),
    ("Round of 32", 83, 93, None),
    ("Round of 32", 84, 93, None),
    # M95 = M86 v M88, M96 = M85 v M87
    ("Round of 32", 85, 96, None),
    ("Round of 32", 86, 95, None),
    ("Round of 32", 87, 96, None),
    ("Round of 32", 88, 95, None),

    # Round of 16 -> Quarterfinal
    ("Round of 16", 89, 97, None),
    ("Round of 16", 90, 97, None),
    ("Round of 16", 91, 98, None),
    ("Round of 16", 92, 98, None),
    ("Round of 16", 93, 99, None),
    ("Round of 16", 94, 99, None),
    ("Round of 16", 95, 100, None),
    ("Round of 16", 96, 100, None),

    # Quarterfinal -> Semifinal
    ("Quarter-final", 97, 101, None),
    ("Quarter-final", 98, 101, None),
    ("Quarter-final", 99, 102, None),
    ("Quarter-final", 100, 102, None),

    # Semifinal -> Final / Third Place
    ("Semi-final", 101, 104, 103),
    ("Semi-final", 102, 104, 103),

    # Terminal matches
    ("Third Place", 103, None, None),
    ("Final", 104, None, None),
]

# ============================================================================
# Helpers
# ============================================================================


def _resolve_team_id(conn: sqlite3.Connection, name: str) -> str | None:
    row = conn.execute("SELECT id FROM teams WHERE name = ?", (name,)).fetchone()
    if row:
        return row[0]
    # fuzzy fallback
    row = conn.execute(
        "SELECT id FROM teams WHERE name LIKE ?", (f"%{name}%",)
    ).fetchone()
    return row[0] if row else None


def _resolve_tbd_id(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT id FROM teams WHERE name = 'TBD'").fetchone()
    if not row:
        raise RuntimeError("TBD team not found in teams table")
    return row[0]


# ============================================================================
# Fix 1: Group-stage matches
# ============================================================================


def fix_group_matches(conn: sqlite3.Connection, dry_run: bool = False) -> int:
    """Update 72 group-stage match dates + fix incorrect team pairings.

    Groups spec entries and DB rows by stage, then finds the optimal 1:1
    mapping using a greedy minimum-distance algorithm.
    """
    updated = 0

    # Group spec entries by stage
    spec_by_stage: dict[str, list[tuple]] = defaultdict(list)
    for item in GROUP_MATCHES:
        spec_by_stage[item[3]].append(item)

    for stage, spec_entries in spec_by_stage.items():
        db_rows = conn.execute(
            """SELECT m.id, m.match_date, ht.name as h, at.name as a,
                      m.home_team_id, m.away_team_id
               FROM matches m
               JOIN teams ht ON m.home_team_id = ht.id
               JOIN teams at ON m.away_team_id = at.id
               WHERE m.competition LIKE '%World Cup 2026%'
                 AND m.stage = ?
               ORDER BY m.id""",
            (stage,),
        ).fetchall()

        unmatched = list(db_rows)

        for match_date_utc, home, away, _ in spec_entries:
            home_id = _resolve_team_id(conn, home)
            away_id = _resolve_team_id(conn, away)
            if not home_id or not away_id:
                print(f"  WARN: team not found - {home} vs {away}")
                continue

            # Greedy best-match among unmatched rows
            best = None
            best_score = 99

            for db_row in unmatched:
                score = 99
                if db_row["h"] == home and db_row["a"] == away:
                    score = 0  # exact
                elif db_row["h"] == away and db_row["a"] == home:
                    score = 1  # swapped
                elif db_row["h"] == home:
                    score = 2  # home matches
                elif db_row["a"] == away:
                    score = 3  # away matches
                elif db_row["h"] == away:
                    score = 4
                elif db_row["a"] == home:
                    score = 5
                else:
                    continue

                if score < best_score:
                    best_score = score
                    best = db_row

            if best is None:
                print(f"  WARN: no match for {home} vs {away} in {stage}")
                continue

            unmatched.remove(best)

            if dry_run:
                flag = "=" if best["h"] == home and best["a"] == away else "~"
                print(f"  [DRY] {flag} {home} vs {away}: "
                      f"[{best['h']} vs {best['a']}] "
                      f"{best['match_date']} -> {match_date_utc}")
            else:
                conn.execute(
                    """UPDATE matches
                       SET match_date = ?, home_team_id = ?, away_team_id = ?
                       WHERE id = ?""",
                    (match_date_utc, home_id, away_id, best["id"]),
                )
            updated += 1

    return updated


# ============================================================================
# Fix 2: wc26_schedule
# ============================================================================


def fix_wc26_schedule(conn: sqlite3.Connection, dry_run: bool = False) -> int:
    """Update wc26_schedule: group-stage dates + knockout dates/times."""
    updated = 0

    # -- Group stage (M1-M72): match by team names --
    for match_date_utc, home, away, stage in GROUP_MATCHES:
        date_part = match_date_utc[:10]
        time_part = match_date_utc[11:16]

        row = conn.execute(
            """SELECT id, match_date, kickoff_time, home_team, away_team
               FROM wc26_schedule
               WHERE home_team = ? AND away_team = ?
                 AND stage = 'Group Stage'""",
            (home, away),
        ).fetchone()

        if not row:
            row = conn.execute(
                """SELECT id, match_date, kickoff_time, home_team, away_team
                   FROM wc26_schedule
                   WHERE home_team = ? AND away_team = ?
                     AND stage = 'Group Stage'""",
                (away, home),
            ).fetchone()

        if row:
            if dry_run:
                if row["match_date"] != date_part:
                    print(f"  [DRY] sched {home}-{away}: "
                          f"{row['match_date']} {row['kickoff_time']} -> {date_part} {time_part}")
            else:
                conn.execute(
                    "UPDATE wc26_schedule SET match_date=?, kickoff_time=? WHERE id=?",
                    (date_part, time_part, row["id"]),
                )
            updated += 1

    # -- Knockout (M73-M104): match by match_number --
    for i, (date_utc, stage_name, home_slot, away_slot) in enumerate(KNOCKOUT_MATCHES):
        match_num = 73 + i
        date_part = date_utc[:10]
        time_part = date_utc[11:16]

        sched_rows = conn.execute(
            "SELECT id, match_date FROM wc26_schedule WHERE match_number = ?",
            (match_num,),
        ).fetchall()

        if len(sched_rows) == 1:
            row = sched_rows[0]
            if dry_run:
                print(f"  [DRY] sched M{match_num}: "
                      f"{row['match_date']} -> {date_part} {time_part}")
            else:
                conn.execute(
                    """UPDATE wc26_schedule
                       SET match_date=?, kickoff_time=?, stage=?
                       WHERE match_number=?""",
                    (date_part, time_part, stage_name, match_num),
                )
            updated += 1
        elif len(sched_rows) > 1:
            # Multiple rows for same match number - update all
            for row in sched_rows:
                if not dry_run:
                    conn.execute(
                        """UPDATE wc26_schedule
                           SET match_date=?, kickoff_time=?, stage=?
                           WHERE id=?""",
                        (date_part, time_part, stage_name, row["id"]),
                    )
                updated += 1

    return updated


# ============================================================================
# Fix 3: Knockout-stage matches
# ============================================================================


def fix_knockout_matches(conn: sqlite3.Connection, dry_run: bool = False) -> int:
    """Update 32 knockout-match dates + opponent slot labels.

    Orders matches by id within each stage for deterministic 1:1 mapping.
    """
    tbd_id = _resolve_tbd_id(conn)

    stage_order = [
        "Round of 32", "Round of 16", "Quarterfinal",
        "Semifinal", "Third Place Playoff", "Final",
    ]

    spec_by_stage: dict[str, list[tuple]] = defaultdict(list)
    for entry in KNOCKOUT_MATCHES:
        spec_by_stage[entry[1]].append(entry)

    updated = 0
    for stage_name in stage_order:
        spec_list = spec_by_stage.get(stage_name, [])
        if not spec_list:
            continue

        rows = conn.execute(
            """SELECT id, match_date FROM matches
               WHERE competition LIKE '%World Cup 2026%'
                 AND stage = ? AND home_team_id = ?
               ORDER BY id""",
            (stage_name, tbd_id),
        ).fetchall()

        if len(rows) != len(spec_list):
            print(f"  WARN: {stage_name} count mismatch: "
                  f"DB={len(rows)}, spec={len(spec_list)}")

        for i, (row, (new_date, _, home_slot, away_slot)) in enumerate(
            zip(rows, spec_list)
        ):
            new_stage = f"{stage_name} - {home_slot} vs {away_slot}"

            if dry_run:
                print(f"  [DRY] KO id={row['id'][:8]}: "
                      f"{row['match_date']} -> {new_date} | {new_stage}")
            else:
                conn.execute(
                    "UPDATE matches SET match_date=?, stage=? WHERE id=?",
                    (new_date, new_stage, row["id"]),
                )
            updated += 1

    return updated


# ============================================================================
# Fix 4: Knockout paths
# ============================================================================


def rebuild_knockout_paths(conn: sqlite3.Connection, dry_run: bool = False) -> int:
    """Delete all wc26_knockout_paths rows and re-insert correct bracket."""
    if dry_run:
        existing = conn.execute(
            "SELECT count(*) FROM wc26_knockout_paths"
        ).fetchone()[0]
        print(f"  [DRY] DELETE {existing} rows, INSERT {len(CORRECT_KNOCKOUT_PATHS)} rows")
        return existing + len(CORRECT_KNOCKOUT_PATHS)

    conn.execute("DELETE FROM wc26_knockout_paths")
    now = datetime.utcnow().isoformat()
    inserted = 0
    for round_name, match_num, winner_to, loser_to in CORRECT_KNOCKOUT_PATHS:
        conn.execute(
            """INSERT INTO wc26_knockout_paths
               (round, match_number, winner_advances_to_match,
                loser_advances_to_match, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (round_name, match_num, winner_to, loser_to, now),
        )
        inserted += 1
    return inserted


# ============================================================================
# Verification
# ============================================================================


def print_verification(conn: sqlite3.Connection):
    print("\n=== Verify: Group stage date distribution ===")
    rows = conn.execute("""
        SELECT date(match_date) as d, count(*) as cnt
        FROM matches WHERE competition LIKE '%World Cup 2026%' AND stage LIKE '%Group%'
        GROUP BY d ORDER BY d
    """).fetchall()
    for r in rows:
        bar = "#" * r["cnt"]
        print(f"  {r['d']}: {r['cnt']:2d} matches {bar}")
    print(f"  Total: {sum(r['cnt'] for r in rows)} (expected 72)")
    print(f"  Days:  {len(rows)} (expected 17)")

    print("\n=== Verify: Knockout date distribution ===")
    rows = conn.execute("""
        SELECT date(match_date) as d, count(*) as cnt
        FROM matches WHERE competition LIKE '%World Cup 2026%'
          AND (stage LIKE '%Round%' OR stage LIKE '%Quarter%'
               OR stage LIKE '%Semi%' OR stage LIKE '%Final%' OR stage LIKE '%Third%')
        GROUP BY d ORDER BY d
    """).fetchall()
    for r in rows:
        print(f"  {r['d']}: {r['cnt']} matches")
    print(f"  Total: {sum(r['cnt'] for r in rows)} (expected 32)")

    print("\n=== Verify: Knockout paths (first 5 + last 5) ===")
    rows = conn.execute("""
        SELECT round, match_number, winner_advances_to_match, loser_advances_to_match
        FROM wc26_knockout_paths
        ORDER BY
            CASE round
                WHEN 'Round of 32' THEN 1 WHEN 'Round of 16' THEN 2
                WHEN 'Quarter-final' THEN 3 WHEN 'Semi-final' THEN 4
                WHEN 'Third Place' THEN 5 WHEN 'Final' THEN 6
            END, match_number
    """).fetchall()
    for r in rows[:5]:
        w = f"M{r['winner_advances_to_match']}" if r["winner_advances_to_match"] else "-"
        l = f"M{r['loser_advances_to_match']}" if r["loser_advances_to_match"] else ""
        print(f"  {r['round']:20s} | M{r['match_number']:3d} -> winner:{w:5s}  loser:{l}")
    print("  ...")
    for r in rows[-5:]:
        w = f"M{r['winner_advances_to_match']}" if r["winner_advances_to_match"] else "-"
        l = f"M{r['loser_advances_to_match']}" if r["loser_advances_to_match"] else ""
        print(f"  {r['round']:20s} | M{r['match_number']:3d} -> winner:{w:5s}  loser:{l}")

    print(f"\n  Total paths: {len(rows)}")


# ============================================================================
# Main
# ============================================================================


def main():
    parser = argparse.ArgumentParser(description="WC26 schedule fix V3.7.2")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db-path", default=str(DB_PATH))
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"ERROR: DB not found: {db_path}")
        sys.exit(1)

    print("=" * 60)
    print("WC26 Schedule Fix V3.7.2")
    print(f"DB: {db_path}")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'EXECUTE'}")
    print("=" * 60)

    if not args.dry_run:
        backup_path = db_path.with_suffix(
            f".db.bak-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        shutil.copy2(db_path, backup_path)
        print(f"\n[OK] Backup: {backup_path.name}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")

    try:
        print("\n-- Fix 1: matches group stage (72 matches) --")
        g = fix_group_matches(conn, dry_run=args.dry_run)
        print(f"  Group matches updated: {g}")

        print("\n-- Fix 2: wc26_schedule --")
        s = fix_wc26_schedule(conn, dry_run=args.dry_run)
        print(f"  Schedule updated: {s}")

        print("\n-- Fix 3: matches knockout (32 matches) --")
        k = fix_knockout_matches(conn, dry_run=args.dry_run)
        print(f"  Knockout matches updated: {k}")

        print("\n-- Fix 4: wc26_knockout_paths --")
        p = rebuild_knockout_paths(conn, dry_run=args.dry_run)
        print(f"  Knockout paths rebuilt: {p}")

        if not args.dry_run:
            conn.commit()
            print("\n[OK] All fixes committed.")
            print_verification(conn)
        else:
            conn.rollback()
            print("\n[INFO] DRY-RUN - no changes written.")

    except Exception as e:
        conn.rollback()
        print(f"\n[FAIL] {e}")
        raise
    finally:
        conn.close()

    print("\n" + "=" * 60)
    if not args.dry_run:
        print("Done. Re-run prediction pipeline to verify.")
    print("=" * 60)


if __name__ == "__main__":
    main()

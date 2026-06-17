#!/usr/bin/env python3
"""Audit DB schedule against official FIFA 2026 schedule (Beijing time)."""
import sqlite3
from pathlib import Path

DB_PATH = Path(r"D:\hermes agent\2026世界杯分析\backend\data\local_stage2.db")

# Official schedule — source: FIFA via Tencent News / 2026globalcup / football2026tips
# All times Beijing (UTC+8). Format: (date, time): (group, home, away, round)
OFFICIAL = {
    # ===== Round 1 =====
    ("2026-06-12", "03:00"): ("A", "Mexico", "South Africa", "R1"),
    ("2026-06-12", "10:00"): ("A", "South Korea", "Czech Republic", "R1"),
    ("2026-06-13", "03:00"): ("B", "Canada", "Bosnia and Herzegovina", "R1"),
    ("2026-06-13", "09:00"): ("D", "United States", "Paraguay", "R1"),
    ("2026-06-13", "12:00"): ("D", "Australia", "Turkey", "R1"),
    ("2026-06-14", "03:00"): ("B", "Qatar", "Switzerland", "R1"),
    ("2026-06-14", "06:00"): ("C", "Brazil", "Morocco", "R1"),
    ("2026-06-14", "09:00"): ("C", "Haiti", "Scotland", "R1"),
    ("2026-06-15", "01:00"): ("E", "Germany", "Curacao", "R1"),
    ("2026-06-15", "04:00"): ("F", "Netherlands", "Japan", "R1"),
    ("2026-06-15", "07:00"): ("E", "Ivory Coast", "Ecuador", "R1"),
    ("2026-06-15", "10:00"): ("F", "Tunisia", "Sweden", "R1"),
    ("2026-06-16", "00:00"): ("H", "Spain", "Cape Verde", "R1"),
    ("2026-06-16", "03:00"): ("G", "Belgium", "Egypt", "R1"),
    ("2026-06-16", "06:00"): ("H", "Saudi Arabia", "Uruguay", "R1"),
    ("2026-06-16", "09:00"): ("G", "Iran", "New Zealand", "R1"),
    ("2026-06-17", "03:00"): ("I", "France", "Senegal", "R1"),
    ("2026-06-17", "06:00"): ("I", "Iraq", "Norway", "R1"),
    ("2026-06-17", "09:00"): ("J", "Argentina", "Algeria", "R1"),
    ("2026-06-17", "12:00"): ("J", "Austria", "Jordan", "R1"),
    ("2026-06-18", "01:00"): ("K", "Portugal", "DR Congo", "R1"),
    ("2026-06-18", "04:00"): ("L", "England", "Croatia", "R1"),
    ("2026-06-18", "07:00"): ("L", "Ghana", "Panama", "R1"),
    ("2026-06-18", "10:00"): ("K", "Uzbekistan", "Colombia", "R1"),
    # ===== Round 2 =====
    ("2026-06-19", "00:00"): ("A", "Czech Republic", "South Africa", "R2"),
    ("2026-06-19", "03:00"): ("B", "Switzerland", "Bosnia and Herzegovina", "R2"),
    ("2026-06-19", "06:00"): ("B", "Canada", "Qatar", "R2"),
    ("2026-06-19", "09:00"): ("A", "Mexico", "South Korea", "R2"),
    ("2026-06-20", "03:00"): ("D", "United States", "Australia", "R2"),
    ("2026-06-20", "06:00"): ("C", "Scotland", "Morocco", "R2"),
    ("2026-06-20", "09:00"): ("C", "Brazil", "Haiti", "R2"),
    ("2026-06-20", "12:00"): ("D", "Turkey", "Paraguay", "R2"),
    ("2026-06-21", "01:00"): ("F", "Netherlands", "Sweden", "R2"),
    ("2026-06-21", "04:00"): ("E", "Germany", "Ivory Coast", "R2"),
    ("2026-06-21", "08:00"): ("E", "Ecuador", "Curacao", "R2"),
    ("2026-06-21", "12:00"): ("F", "Tunisia", "Japan", "R2"),
    ("2026-06-22", "00:00"): ("H", "Spain", "Saudi Arabia", "R2"),
    ("2026-06-22", "03:00"): ("G", "Belgium", "Iran", "R2"),
    ("2026-06-22", "06:00"): ("H", "Uruguay", "Cape Verde", "R2"),
    ("2026-06-22", "09:00"): ("G", "New Zealand", "Egypt", "R2"),
    ("2026-06-23", "01:00"): ("J", "Argentina", "Austria", "R2"),
    ("2026-06-23", "05:00"): ("I", "France", "Iraq", "R2"),
    ("2026-06-23", "08:00"): ("I", "Norway", "Senegal", "R2"),
    ("2026-06-23", "11:00"): ("J", "Jordan", "Algeria", "R2"),
    ("2026-06-24", "01:00"): ("K", "Portugal", "Uzbekistan", "R2"),
    ("2026-06-24", "04:00"): ("L", "England", "Ghana", "R2"),
    ("2026-06-24", "07:00"): ("L", "Panama", "Croatia", "R2"),
    ("2026-06-24", "10:00"): ("K", "Colombia", "DR Congo", "R2"),
    # ===== Round 3 =====
    ("2026-06-25", "03:00"): ("B", "Switzerland", "Canada", "R3"),
    ("2026-06-25", "03:00"): ("B", "Bosnia and Herzegovina", "Qatar", "R3"),
    ("2026-06-25", "06:00"): ("C", "Scotland", "Brazil", "R3"),
    ("2026-06-25", "06:00"): ("C", "Morocco", "Haiti", "R3"),
    ("2026-06-25", "09:00"): ("A", "Czech Republic", "Mexico", "R3"),
    ("2026-06-25", "09:00"): ("A", "South Africa", "South Korea", "R3"),
    ("2026-06-26", "04:00"): ("E", "Ecuador", "Germany", "R3"),
    ("2026-06-26", "04:00"): ("E", "Curacao", "Ivory Coast", "R3"),
    ("2026-06-26", "07:00"): ("F", "Japan", "Sweden", "R3"),
    ("2026-06-26", "07:00"): ("F", "Tunisia", "Netherlands", "R3"),
    ("2026-06-26", "10:00"): ("D", "Turkey", "United States", "R3"),
    ("2026-06-26", "10:00"): ("D", "Paraguay", "Australia", "R3"),
    ("2026-06-27", "03:00"): ("I", "Norway", "France", "R3"),
    ("2026-06-27", "03:00"): ("I", "Senegal", "Iraq", "R3"),
    ("2026-06-27", "08:00"): ("H", "Cape Verde", "Saudi Arabia", "R3"),
    ("2026-06-27", "08:00"): ("H", "Uruguay", "Spain", "R3"),
    ("2026-06-27", "11:00"): ("G", "Egypt", "Iran", "R3"),
    ("2026-06-27", "11:00"): ("G", "New Zealand", "Belgium", "R3"),
    ("2026-06-28", "05:00"): ("L", "Panama", "England", "R3"),
    ("2026-06-28", "05:00"): ("L", "Croatia", "Ghana", "R3"),
    ("2026-06-28", "07:30"): ("K", "Colombia", "Portugal", "R3"),
    ("2026-06-28", "07:30"): ("K", "DR Congo", "Uzbekistan", "R3"),
    ("2026-06-28", "10:00"): ("J", "Algeria", "Austria", "R3"),
    ("2026-06-28", "10:00"): ("J", "Jordan", "Argentina", "R3"),
}

# Official knockout dates (Beijing time) — first/last dates per stage
OFFICIAL_KO = {
    "Round of 32":  ("2026-06-29", "2026-07-04"),
    "Round of 16":  ("2026-07-05", "2026-07-08"),
    "Quarterfinal": ("2026-07-10", "2026-07-12"),
    "Semifinal":    ("2026-07-15", "2026-07-16"),
    "Third Place Playoff": ("2026-07-19", "2026-07-19"),
    "Final":        ("2026-07-20", "2026-07-20"),
}


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # ===== Group stage comparison =====
    print("=" * 60)
    print("GROUP STAGE AUDIT")
    print("=" * 60)

    c.execute("""SELECT m.match_date, ht.name as home, at.name as away, m.stage
        FROM matches m
        JOIN teams ht ON ht.id = m.home_team_id
        JOIN teams at ON at.id = m.away_team_id
        WHERE m.competition LIKE '%World Cup 2026%' AND m.stage LIKE 'Group%'
        ORDER BY m.match_date""")
    db_rows = c.fetchall()

    db_by_grp_round = {}
    for r in db_rows:
        stage = r["stage"]
        grp = stage.split(" - ")[0].replace("Group ", "")
        md = stage.split(" - ")[1].replace("Matchday ", "")
        key = (grp, md)
        db_by_grp_round.setdefault(key, []).append((r["home"], r["away"], r["match_date"]))

    off_by_grp_round = {}
    for (d, t), (grp, home, away, rnd) in OFFICIAL.items():
        key = (grp, rnd.replace("R", ""))
        off_by_grp_round.setdefault(key, []).append((home, away, d, t))

    matchup_issues = []
    date_issues = []
    all_good = 0

    for grp in ["A","B","C","D","E","F","G","H","I","J","K","L"]:
        for md in ["1","2","3"]:
            key = (grp, md)
            off = off_by_grp_round.get(key, [])
            db = db_by_grp_round.get(key, [])

            if not off and not db:
                continue
            if not off:
                matchup_issues.append(f"  Group {grp} R{md}: DB has matches but no official data")
                continue
            if not db:
                matchup_issues.append(f"  Group {grp} R{md}: MISSING from DB!")
                continue

            off_pairs = {tuple(sorted([h, a])) for h, a, *_ in off}
            db_pairs = {tuple(sorted([h, a])) for h, a, _ in db}

            if off_pairs == db_pairs:
                all_good += 1
            else:
                only_off = off_pairs - db_pairs
                only_db = db_pairs - off_pairs
                msg = f"  Group {grp} R{md} MISMATCH:"
                if only_off:
                    msg += f" Missing from DB: {only_off}"
                if only_db:
                    msg += f" Extra in DB: {only_db}"
                matchup_issues.append(msg)

            for h, a, db_date in db:
                off_match = [(d, t) for (o_h, o_a, d, t) in off if tuple(sorted([o_h, o_a])) == tuple(sorted([h, a]))]
                if off_match:
                    off_date = off_match[0][0]
                    if off_date != db_date:
                        date_issues.append(f"  {h} vs {a}: DB={db_date}, Official=Beijing {off_date} {off_match[0][1]}")

    print(f"\nMatchups correct: {all_good}/36 groups-rounds")
    print(f"\n--- MATCHUP ISSUES ({len(matchup_issues)}) ---")
    for i in matchup_issues:
        print(i)

    print(f"\n--- DATE ISSUES ({len(date_issues)}) ---")
    for i in date_issues:
        print(i)

    # DB dates summary
    print(f"\n--- DB GROUP DATES ---")
    c.execute("""SELECT date(m.match_date) as d, count(*) as cnt
        FROM matches m WHERE m.competition LIKE '%World Cup 2026%' AND m.stage LIKE 'Group%'
        GROUP BY d ORDER BY d""")
    for r in c.fetchall():
        print(f"  {r['d']}: {r['cnt']} matches")

    print(f"\n--- OFFICIAL GROUP DATES (Beijing) ---")
    off_dates = {}
    for (d, t), _ in OFFICIAL.items():
        off_dates[d] = off_dates.get(d, 0) + 1
    for d in sorted(off_dates):
        print(f"  {d}: {off_dates[d]} matches")

    # ===== Knockout comparison =====
    print("\n" + "=" * 60)
    print("KNOCKOUT STAGE AUDIT")
    print("=" * 60)

    c.execute("""SELECT DISTINCT date(m.match_date) as d, m.stage
        FROM matches m
        WHERE m.competition LIKE '%World Cup 2026%' AND m.stage NOT LIKE 'Group%'
        ORDER BY m.match_date""")
    ko_rows = c.fetchall()

    db_ko = {}
    for r in ko_rows:
        db_ko.setdefault(r["stage"], []).append(r["d"])

    for stage, (off_start, off_end) in OFFICIAL_KO.items():
        db_dates = db_ko.get(stage, [])
        if not db_dates:
            print(f"  {stage}: MISSING from DB!")
            continue
        db_start = min(db_dates)
        db_end = max(db_dates)
        ok = (db_start == off_start and db_end == off_end)
        mark = "OK" if ok else "MISMATCH"
        print(f"  {stage}: DB={db_start}~{db_end} vs Official={off_start}~{off_end} [{mark}]")

    print(f"\n--- DB KNOCKOUT DATES ---")
    for r in ko_rows:
        print(f"  {r['d']}: {r['stage']}")

    # ===== Summary =====
    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    print(f"Group matchup issues:  {len(matchup_issues)}")
    print(f"Group date mismatches: {len(date_issues)}")
    print(f"Total DB group matches: {sum(len(v) for v in db_by_grp_round.values())}")
    print(f"Total official group matches: {len(OFFICIAL)}")

    conn.close()


if __name__ == "__main__":
    main()

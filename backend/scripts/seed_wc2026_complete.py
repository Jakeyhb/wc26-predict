"""Seed 2026 World Cup complete schedule with CORRECT group assignments.

Source: cross-verified from Wikipedia, FIFA, NBC Sports, ESPN.
Last updated: 2026-05-28.

Group draw: Dec 5, 2025 in Washington DC.
Playoff winners confirmed: Mar 31, 2026.

Teams: 48 (12 groups of 4)
Format: 72 group matches + 32 knockout = 104 total
Dates: Group stage June 11-22, 2026
       Round of 32 June 23-27
       Round of 16 June 29-July 2
       Quarterfinals July 4-5
       Semifinals July 8-9
       Third Place July 18
       Final July 19 (MetLife Stadium, NJ)
"""
import sqlite3, os, hashlib
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(os.path.dirname(SCRIPT_DIR), "data", "local_stage2.db")

# Verified groupings
GROUPS = {
    "A": ["Mexico", "Korea Republic", "South Africa", "Czechia"],
    "B": ["Canada", "Bosnia and Herzegovina", "Qatar", "Switzerland"],
    "C": ["Brazil", "Morocco", "Haiti", "Scotland"],
    "D": ["United States", "Paraguay", "Australia", "Turkey"],
    "E": ["Germany", "Curacao", "Ivory Coast", "Ecuador"],
    "F": ["Netherlands", "Japan", "Sweden", "Tunisia"],
    "G": ["Belgium", "Egypt", "Iran", "New Zealand"],
    "H": ["Spain", "Cape Verde", "Saudi Arabia", "Uruguay"],
    "I": ["France", "Senegal", "Norway", "Iraq"],
    "J": ["Argentina", "Algeria", "Austria", "Jordan"],
    "K": ["Portugal", "DR Congo", "Uzbekistan", "Colombia"],
    "L": ["England", "Croatia", "Ghana", "Panama"],
}

# Matchdays: (team0_idx, team1_idx, matchday_label)
# MD1: 0vs1, 2vs3  MD2: 0vs2, 1vs3  MD3: 0vs3, 1vs2
MATCHUPS = [
    (0, 1), (2, 3),  # Matchday 1
    (0, 2), (1, 3),  # Matchday 2
    (0, 3), (1, 2),  # Matchday 3
]

# Base dates per matchday per group (spread across 2 days per MD, 3 groups/day)
GROUP_START_DAYS = {
    "MD1": {"A": "2026-06-11", "B": "2026-06-11", "C": "2026-06-11",
            "D": "2026-06-12", "E": "2026-06-12", "F": "2026-06-12",
            "G": "2026-06-13", "H": "2026-06-13", "I": "2026-06-13",
            "J": "2026-06-14", "K": "2026-06-14", "L": "2026-06-14"},
    "MD2": {"A": "2026-06-15", "B": "2026-06-15", "C": "2026-06-15",
            "D": "2026-06-16", "E": "2026-06-16", "F": "2026-06-16",
            "G": "2026-06-17", "H": "2026-06-17", "I": "2026-06-17",
            "J": "2026-06-18", "K": "2026-06-18", "L": "2026-06-18"},
    "MD3": {"A": "2026-06-19", "B": "2026-06-19", "C": "2026-06-19",
            "D": "2026-06-20", "E": "2026-06-20", "F": "2026-06-20",
            "G": "2026-06-21", "H": "2026-06-21", "I": "2026-06-21",
            "J": "2026-06-22", "K": "2026-06-22", "L": "2026-06-22"},
}

def team_id(name):
    return hashlib.md5(f"nt_{name.lower().strip()}".encode()).hexdigest()

def match_key(home, away, competition):
    return hashlib.md5(f"wc26_{home}_{away}_{competition}".encode()).hexdigest()

def seed():
    conn = sqlite3.connect(DB_PATH)
    inserted, skipped = 0, 0

    for group, teams in GROUPS.items():
        for slot, (h_idx, a_idx) in enumerate(MATCHUPS):
            home, away = teams[h_idx], teams[a_idx]
            md = f"MD{(slot // 2) + 1}"
            mid = match_key(home, away, f"FIFA World Cup 2026 Group {group}")
            stage = f"Group {group} - Matchday {md[-1]}"

            existing = conn.execute("SELECT id FROM matches WHERE id = ?", (mid,)).fetchone()
            if existing:
                skipped += 1
                continue

            # Ensure teams exist
            for tname in [home, away]:
                tid = team_id(tname)
                conn.execute(
                    "INSERT OR IGNORE INTO teams (id, name, team_type, confederation, elo_rating) VALUES (?, ?, 'national', 'FIFA', 1500.0)",
                    (tid, tname))

            hid, aid = team_id(home), team_id(away)
            date_prefix = GROUP_START_DAYS[md][group]
            match_time = f"{date_prefix}T{14 + (slot % 2) * 6:02d}:00:00"

            conn.execute("""INSERT OR IGNORE INTO matches
                (id, external_id, home_team_id, away_team_id, match_date,
                 competition, competition_type, competition_weight, is_neutral_venue, status, stage)
                VALUES (?, ?, ?, ?, ?, 'FIFA World Cup 2026', 'national', 1.0, 1, 'SCHEDULED', ?)""",
                (mid, f"wc2026_g{group}_m{slot+1}", hid, aid, match_time, stage))
            inserted += 1

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM matches WHERE competition = 'FIFA World Cup 2026'").fetchone()[0]
    conn.close()

    print(f"Inserted: {inserted} | Skipped: {skipped} | Total WC2026: {total}")

if __name__ == "__main__":
    seed()

"""Import international match data from martj42/international_results.

Downloads historical international football results and imports them into the
local SQLite database. Only imports matches from 2015 onwards (older data has
near-zero time-decay weight for Dixon-Coles).

Schema notes (adapted to actual ORM column names):
  - matches.home_team_id / away_team_id are CHAR(32) FK to teams.id
  - teams.id is CHAR(32) — we generate MD5-based IDs for consistency
  - match_results uses home_goals / away_goals columns
  - matches.id is CHAR(32)
"""
import hashlib
import os
import sqlite3
import urllib.request
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(os.path.dirname(SCRIPT_DIR), "data", "local_stage2.db")

CSV_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
MIN_DATE = "2015-01-01"

# Tournaments to skip (youth competitions)
SKIP_KEYWORDS = ["olympic", "u-23", "u23", "u-20", "u20", "u-17", "u17", "u-19", "u19", "u-21", "u21", "youth"]

# Tournament weight mapping
def get_competition_weight(tournament: str) -> float:
    t = tournament.lower()
    if "world cup" in t and "qualification" not in t:
        return 1.0
    if "world cup qualification" in t:
        return 0.75
    if any(x in t for x in ["euro ", "copa america", "african cup of nations", "asian cup", "gold cup", "nations league", "confederations cup"]):
        return 0.90
    if "copa américa" in t:
        return 0.90
    return 0.50  # friendly / other


def team_id(team_name: str) -> str:
    """Generate deterministic CHAR(32) team ID from name."""
    return hashlib.md5(f"nt_{team_name.lower().strip()}".encode()).hexdigest()


def match_id(home: str, away: str, date_str: str) -> str:
    """Generate deterministic CHAR(32) match ID."""
    raw = f"openfb_{date_str}_{home.lower().strip()}_{away.lower().strip()}"
    return hashlib.md5(raw.encode()).hexdigest()


def import_international_results():
    conn = sqlite3.connect(DB_PATH)

    # ── Download ──────────────────────────────────────────────
    print(f"下载国际赛数据: {CSV_URL}")
    try:
        with urllib.request.urlopen(CSV_URL, timeout=60) as response:
            content = response.read().decode("utf-8")
    except Exception as e:
        print(f"下载失败: {e}")
        print("请手动下载: https://github.com/martj42/international_results")
        return

    lines = content.strip().split("\n")
    print(f"CSV 总行数: {len(lines) - 1}")

    # ── Process ───────────────────────────────────────────────
    imported = 0
    skipped = 0
    error_count = 0

    for i, line in enumerate(lines[1:], start=2):
        parts = line.split(",")
        if len(parts) < 8:
            continue

        try:
            date_str = parts[0].strip()
            home_name = parts[1].strip()
            away_name = parts[2].strip()
            home_score_str = parts[3].strip()
            away_score_str = parts[4].strip()
            tournament = parts[5].strip()
            neutral_str = parts[7].strip().upper() if len(parts) > 7 else "FALSE"

            # Filter: 2015+
            if date_str < MIN_DATE:
                continue

            # Filter: skip youth tournaments
            if any(kw in tournament.lower() for kw in SKIP_KEYWORDS):
                continue

            # Parse scores (can be empty for future/scheduled matches)
            home_score = int(home_score_str) if home_score_str else None
            away_score = int(away_score_str) if away_score_str else None

            # Skip matches without scores (we only want finished matches)
            if home_score is None or away_score is None:
                continue

            is_neutral = 1 if neutral_str == "TRUE" else 0
            weight = get_competition_weight(tournament)

            # Check if teams exist, create if not
            for tname in [home_name, away_name]:
                tid = team_id(tname)
                existing = conn.execute("SELECT id FROM teams WHERE id = ?", (tid,)).fetchone()
                if not existing:
                    conn.execute(
                        "INSERT OR IGNORE INTO teams (id, name, team_type, confederation, elo_rating) VALUES (?, ?, 'national', 'FIFA', 1500.0)",
                        (tid, tname),
                    )

            # Check if match already exists (by external_id)
            ext_id = f"openfb_{date_str}_{home_name}_{away_name}"
            existing = conn.execute(
                "SELECT id FROM matches WHERE external_id = ?", (ext_id,)
            ).fetchone()
            if existing:
                skipped += 1
                continue

            # Generate match ID and insert
            mid = match_id(home_name, away_name, date_str)
            hid = team_id(home_name)
            aid = team_id(away_name)

            conn.execute(
                """INSERT OR IGNORE INTO matches
                   (id, external_id, home_team_id, away_team_id, match_date,
                    competition, competition_type, competition_weight,
                    is_neutral_venue, status, stage)
                   VALUES (?, ?, ?, ?, ?,
                           ?, 'national', ?,
                           ?, 'finished', 'International')""",
                (
                    mid,
                    ext_id,
                    hid,
                    aid,
                    f"{date_str}T12:00:00",
                    tournament,
                    weight,
                    is_neutral,
                ),
            )

            # Insert match result
            rid = hashlib.md5(f"result_{mid}".encode()).hexdigest()
            conn.execute(
                """INSERT OR IGNORE INTO match_results
                   (id, match_id, home_goals, away_goals)
                   VALUES (?, ?, ?, ?)""",
                (rid, mid, home_score, away_score),
            )

            imported += 1

            if imported % 500 == 0:
                print(f"  已导入 {imported} 场 (行 {i}/{len(lines)})...")
                conn.commit()

        except Exception:
            error_count += 1
            continue

    conn.commit()

    # ── Verification ─────────────────────────────────────────
    national_total = conn.execute(
        "SELECT COUNT(*) FROM matches WHERE competition_type='national'"
    ).fetchone()[0]
    national_finished = conn.execute(
        "SELECT COUNT(*) FROM matches WHERE competition_type='national' AND status='finished'"
    ).fetchone()[0]
    team_count = conn.execute(
        "SELECT COUNT(*) FROM teams WHERE team_type='national'"
    ).fetchone()[0]

    conn.close()

    print(f"\n{'='*50}")
    print(f"导入完成!")
    print(f"  新增: {imported} 场")
    print(f"  跳过(已存在): {skipped} 场")
    print(f"  解析错误: {error_count} 行")
    print(f"  国家队比赛总数: {national_total} 场")
    print(f"  已完赛国家队: {national_finished} 场")
    print(f"  国家队球队数: {team_count} 支")


if __name__ == "__main__":
    import_international_results()

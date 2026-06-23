"""
Update WC schedule status for matches with confirmed post-match review results.

Only updates matches with VERIFIED results from post-match reviews.
Does NOT fabricate or guess results.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "local_stage2.db"

# CONFIRMED results from post-match reviews (with evidence)
CONFIRMED_RESULTS = [
    # (home_team, away_team, home_goals, away_goals, match_status)
    ("Brazil", "Haiti", 3, 0, "FINISHED"),
    ("Spain", "Saudi Arabia", 4, 0, "FINISHED"),
    ("Argentina", "Austria", 2, 0, "FINISHED"),
    ("France", "Iraq", 3, 0, "FINISHED"),
    ("Norway", "Senegal", 3, 2, "FINISHED"),
]


def main():
    db = sqlite3.connect(str(DB_PATH))
    cur = db.cursor()

    print("Updating WC schedule with confirmed post-match results...\n")

    updated = 0
    skipped = 0

    for home, away, hg, ag, status in CONFIRMED_RESULTS:
        # Check current state
        cur.execute(
            "SELECT match_number, match_date, match_status, home_goals, away_goals "
            "FROM wc26_schedule WHERE home_team=? AND away_team=?",
            (home, away)
        )
        row = cur.fetchone()
        if not row:
            print(f"  [NOT FOUND] {home} vs {away}")
            skipped += 1
            continue

        match_num, match_date, current_status, current_hg, current_ag = row
        print(f"  #{match_num} {home} vs {away} ({match_date}): "
              f"{current_status} ({current_hg}-{current_ag}) → {status} ({hg}-{ag})")

        cur.execute(
            "UPDATE wc26_schedule SET match_status=?, home_goals=?, away_goals=? "
            "WHERE home_team=? AND away_team=?",
            (status, hg, ag, home, away)
        )
        updated += 1

    db.commit()

    # Show updated distribution
    cur.execute("SELECT match_status, COUNT(*) FROM wc26_schedule GROUP BY match_status")
    print(f"\nUpdated status distribution:")
    for r in cur.fetchall():
        print(f"  {r[0]}: {r[1]}")

    # Count still-SCHEDULED matches on/before June 23
    cur.execute(
        "SELECT COUNT(*) FROM wc26_schedule "
        "WHERE match_date <= '2026-06-23' AND match_status = 'SCHEDULED'"
    )
    remaining = cur.fetchone()[0]
    print(f"\nStill SCHEDULED with date <= June 23: {remaining}")
    print(f"Updated: {updated}, Skipped: {skipped}")

    db.close()
    print("\nDone!")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Validate and fix player-team associations in the players table.

Checks:
  1. Orphan team_id — players whose team_id doesn't exist in teams table
  2. Suspicious duplicates — same player name across different team_ids
  3. Non-national-team players — players whose team_id belongs to a club, not a national team
  4. Missing key_player flag — known stars not marked as key

Usage:
    python scripts/_fix_players.py --dry-run     # audit only
    python scripts/_fix_players.py               # audit + fix
    python scripts/_fix_players.py --auto-fix    # apply safe fixes automatically
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import sqlite3

DB_PATH = BACKEND_DIR / "data" / "local_stage2.db"


def audit_players(dry_run: bool = True) -> dict:
    """Audit all player records and return issues found."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    issues = {
        "orphan_team_ids": [],
        "duplicate_names": [],
        "non_national_team": [],
        "missing_key_flag": [],
        "suspicious_club_mismatch": [],
    }

    # ── 1. Orphan team_id ──
    orphans = conn.execute("""
        SELECT p.id, p.name, p.team_id, p.current_club, t.name as team_name
        FROM players p
        LEFT JOIN teams t ON p.team_id = t.id
        WHERE t.id IS NULL
    """).fetchall()
    issues["orphan_team_ids"] = [dict(r) for r in orphans]

    # ── 2. Duplicate player names across different teams ──
    dupes = conn.execute("""
        SELECT p1.id, p1.name, p1.team_id, t1.name as team_name1,
               p2.id as id2, p2.team_id as team_id2, t2.name as team_name2
        FROM players p1
        JOIN players p2 ON p1.name = p2.name AND p1.id < p2.id
        JOIN teams t1 ON p1.team_id = t1.id
        JOIN teams t2 ON p2.team_id = t2.id
        WHERE p1.team_id != p2.team_id
        ORDER BY p1.name
    """).fetchall()
    issues["duplicate_names"] = [dict(r) for r in dupes]

    # ── 3. Players on non-national teams (should only be national for WC) ──
    non_national = conn.execute("""
        SELECT p.id, p.name, p.team_id, t.name as team_name, t.team_type
        FROM players p
        JOIN teams t ON p.team_id = t.id
        WHERE t.team_type != 'national'
        ORDER BY p.name
    """).fetchall()
    issues["non_national_team"] = [dict(r) for r in non_national]

    # ── 4. Known key players not flagged ──
    # Famous players that should be is_key_player=1 but aren't
    known_stars = [
        "Harry Kane", "Kylian Mbappé", "Lionel Messi", "Cristiano Ronaldo",
        "Kevin De Bruyne", "Vinícius Júnior", "Jude Bellingham", "Rodri",
        "Jamal Musiala", "Federico Valverde", "Luka Modrić", "Achraf Hakimi",
        "Virgil van Dijk", "Bruno Fernandes", "Christian Pulišić",
        "Santiago Giménez", "Mohamed Salah", "Robert Lewandowski",
    ]
    placeholders = ",".join("?" for _ in known_stars)
    missing_key = conn.execute(f"""
        SELECT p.id, p.name, p.team_id, t.name as team_name, p.importance_level
        FROM players p
        JOIN teams t ON p.team_id = t.id
        WHERE p.name IN ({placeholders})
          AND p.is_key_player = 0
    """, known_stars).fetchall()
    issues["missing_key_flag"] = [dict(r) for r in missing_key]

    # ── 5. Suspicious club-team mismatches ──
    # Players whose current_club field suggests a different team
    mismatches = conn.execute("""
        SELECT p.id, p.name, p.team_id, t.name as team_name, p.current_club
        FROM players p
        JOIN teams t ON p.team_id = t.id
        WHERE p.current_club IS NOT NULL
          AND p.current_club != ''
          AND t.name NOT LIKE '%' || p.current_club || '%'
          AND p.current_club NOT LIKE '%' || t.name || '%'
    """).fetchall()
    issues["suspicious_club_mismatch"] = [dict(r) for r in mismatches]

    conn.close()
    return issues


def apply_fixes(issues: dict) -> int:
    """Apply safe, non-destructive fixes. Returns count of fixes applied."""
    conn = sqlite3.connect(str(DB_PATH))
    fixed = 0

    # Fix 1: Flag known stars as key players
    for row in issues.get("missing_key_flag", []):
        try:
            conn.execute(
                "UPDATE players SET is_key_player = 1, importance_level = 'key' WHERE id = ?",
                (row["id"],),
            )
            fixed += 1
        except Exception:
            pass

    # Fix 2: Orphan team_id — try to find correct team by name matching
    # (Only if auto-fix is enabled; these are risky)
    # Skipped for now — manual review needed

    conn.commit()
    conn.close()
    return fixed


def print_report(issues: dict) -> None:
    """Print a human-readable audit report."""
    total = sum(len(v) for v in issues.values())

    print("\n" + "=" * 60)
    print("  PLAYERS TABLE AUDIT REPORT")
    print("=" * 60)

    sections = [
        ("orphan_team_ids", "[CRIT] Orphan team_id (team doesn't exist)"),
        ("duplicate_names", "[WARN] Duplicate names across different teams"),
        ("non_national_team", "[WARN] Players on non-national teams"),
        ("missing_key_flag", "[INFO] Known stars missing key_player flag"),
        ("suspicious_club_mismatch", "[INFO] Club name mismatch with team"),
    ]

    for key, label in sections:
        items = issues.get(key, [])
        print(f"\n{label}: {len(items)} found")
        if items:
            for item in items[:10]:  # Show first 10
                if key == "orphan_team_ids":
                    print(f"  - {item['name']} (team_id={item['team_id'][:20]}...) team not found")
                elif key == "duplicate_names":
                    print(f"  - {item['name']}: {item['team_name1']} vs {item['team_name2']}")
                elif key == "non_national_team":
                    print(f"  - {item['name']} → {item['team_name']} ({item['team_type']})")
                elif key == "missing_key_flag":
                    print(f"  - {item['name']} ({item['team_name']}) level={item['importance_level']}")
                elif key == "suspicious_club_mismatch":
                    print(f"  - {item['name']}: DB={item['team_name']} club={item['current_club']}")
            if len(items) > 10:
                print(f"  ... and {len(items) - 10} more")

    print(f"\n{'=' * 60}")
    print(f"  TOTAL ISSUES: {total}")
    print("=" * 60)

    if total == 0:
        print("\n[OK] Players table is clean — no issues found.")
    else:
        print("\nRun with --auto-fix to apply safe fixes (missing key_player flags only).")
        print("Other issues may require manual review.")


def main():
    parser = argparse.ArgumentParser(description="Audit and fix player-team associations")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Audit only, no writes (default)")
    parser.add_argument("--auto-fix", action="store_true",
                        help="Apply safe automatic fixes")
    args = parser.parse_args()

    print("Auditing players table...")
    issues = audit_players(dry_run=args.dry_run)
    print_report(issues)

    if args.auto_fix and not args.dry_run:
        fixed = apply_fixes(issues)
        print(f"\n[FIXED] Applied {fixed} safe fixes.")
    elif args.auto_fix:
        print("\n[Dry run] No fixes applied. Remove --dry-run to apply.")


if __name__ == "__main__":
    main()

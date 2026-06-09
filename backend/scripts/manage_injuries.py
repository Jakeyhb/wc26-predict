"""manage_injuries.py — CLI for maintaining the injuries.json seed data file.

Usage:
    # List all injuries
    python scripts/manage_injuries.py list

    # List injuries for a specific team
    python scripts/manage_injuries.py list --team "China PR"

    # Add an injury
    python scripts/manage_injuries.py add \
        --player "Kylian Mbappe" --team "France" \
        --status doubtful --type "hamstring" \
        --return "2026-06-20" --confidence 0.8 --source "L'Equipe"

    # Remove an injury (by player + team match)
    python scripts/manage_injuries.py remove --player "Kylian Mbappe" --team "France"

    # Purge all example/placeholder entries
    python scripts/manage_injuries.py purge-examples
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
INJURIES_PATH = BACKEND_DIR / "data" / "injuries.json"


def _load() -> list[dict[str, Any]]:
    if not INJURIES_PATH.exists():
        return []
    with open(INJURIES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    # Filter out comment-only entries
    return [d for d in data if "player_name" in d]


def _save(records: list[dict[str, Any]]) -> None:
    with open(INJURIES_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(records)} injury records to {INJURIES_PATH}")


def cmd_list(args: argparse.Namespace) -> None:
    records = _load()
    if args.team:
        records = [r for r in records if r.get("team_name", "").lower() == args.team.lower()]

    if not records:
        print("No injury records found.")
        return

    print(f"{'Player':<30} {'Team':<20} {'Status':<12} {'Type':<15} {'Return':<12} {'Conf':<6} {'Source'}")
    print("-" * 120)
    for r in records:
        print(
            f"{r['player_name']:<30} {r['team_name']:<20} {r.get('status', '?'):<12} "
            f"{r.get('injury_type', '?'):<15} {r.get('expected_return', 'N/A') or 'N/A':<12} "
            f"{r.get('confidence', 0):<6.0%} {r.get('source', '?')}"
        )


def cmd_add(args: argparse.Namespace) -> None:
    records = _load()

    # Check for duplicates
    for r in records:
        if r.get("player_name") == args.player and r.get("team_name") == args.team:
            print(
                f"WARNING: {args.player} ({args.team}) already exists. "
                "Use remove first or edit manually."
            )
            return

    records.append({
        "player_name": args.player,
        "team_name": args.team,
        "status": args.status,
        "injury_type": args.type,
        "expected_return": args.return_date or None,
        "confidence": args.confidence,
        "source": args.source,
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })

    _save(records)
    print(f"Added: {args.player} ({args.team}) — {args.status}")


def cmd_remove(args: argparse.Namespace) -> None:
    records = _load()
    before = len(records)
    records = [
        r for r in records
        if not (r.get("player_name") == args.player and r.get("team_name") == args.team)
    ]
    if len(records) == before:
        print(f"No record found for {args.player} ({args.team})")
    else:
        _save(records)
        print(f"Removed: {args.player} ({args.team})")


def cmd_purge_examples(args: argparse.Namespace) -> None:
    records = _load()
    before = len(records)
    records = [r for r in records if "示例" not in r.get("player_name", "")]
    removed = before - len(records)
    _save(records)
    print(f"Purged {removed} example entries. {len(records)} real records remain.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage injury data for WC26 Predict")
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = sub.add_parser("list", help="List injury records")
    p_list.add_argument("--team", help="Filter by team name")
    p_list.set_defaults(func=cmd_list)

    # add
    p_add = sub.add_parser("add", help="Add an injury record")
    p_add.add_argument("--player", required=True, help="Player name")
    p_add.add_argument("--team", required=True, help="Team name")
    p_add.add_argument("--status", required=True,
                       choices=["out", "doubtful", "probable", "available"],
                       help="Injury status")
    p_add.add_argument("--type", default=None, help="Injury type (e.g. hamstring, knee)")
    p_add.add_argument("--return-date", "--return", default=None,
                       help="Expected return date (YYYY-MM-DD)")
    p_add.add_argument("--confidence", type=float, default=0.7,
                       help="Confidence in the report (0.0-1.0)")
    p_add.add_argument("--source", default="manual", help="Data source")
    p_add.set_defaults(func=cmd_add)

    # remove
    p_rm = sub.add_parser("remove", help="Remove an injury record")
    p_rm.add_argument("--player", required=True, help="Player name")
    p_rm.add_argument("--team", required=True, help="Team name")
    p_rm.set_defaults(func=cmd_remove)

    # purge-examples
    p_purge = sub.add_parser("purge-examples", help="Remove all example entries")
    p_purge.set_defaults(func=cmd_purge_examples)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

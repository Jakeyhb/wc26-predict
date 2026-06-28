#!/usr/bin/env python
"""ingest_web_odds.py — Populate the web odds cache with multi-bookmaker data.

This script is the bridge between Claude's web-search capability and the Python
prediction pipeline. After Claude searches the web for odds from 8+ bookmakers,
this script writes the structured data into _web_odds_cache.json.

Usage:
    # From JSON file (recommended for large datasets):
    python ingest_web_odds.py --home "Brazil" --away "Japan" --file odds_data.json

    # From inline JSON (for small datasets):
    python ingest_web_odds.py --home "Brazil" --away "Japan" --json '[{"name":"Bet365","region":"UK","home":1.75,"draw":3.60,"away":4.75}]'

    # View cache stats:
    python ingest_web_odds.py --stats

    # View a specific match:
    python ingest_web_odds.py --home "Brazil" --away "Japan" --show

Input JSON format:
    [
        {"name": "BetOnline", "region": "US", "home": 1.72, "draw": 3.80, "away": 5.00},
        {"name": "DraftKings", "region": "US", "home": 1.74, "draw": 3.80, "away": 4.90},
        ...
    ]

    Optional O/U and to-advance data can be included via --ou-file and --advance-file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest multi-bookmaker web odds into the cache",
    )
    parser.add_argument("--home", type=str, help="Home team name")
    parser.add_argument("--away", type=str, help="Away team name")
    parser.add_argument(
        "--file", type=str,
        help="JSON file containing bookmaker odds list",
    )
    parser.add_argument(
        "--json", type=str,
        help="Inline JSON string of bookmaker odds list",
    )
    parser.add_argument(
        "--ou-file", type=str,
        help="Optional JSON file with over/under odds per bookmaker",
    )
    parser.add_argument(
        "--advance-file", type=str,
        help="Optional JSON file with to-advance odds per bookmaker",
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Show cache statistics and exit",
    )
    parser.add_argument(
        "--show", action="store_true",
        help="Show a specific match entry and exit",
    )

    args = parser.parse_args()

    # ── Stats mode ──
    if args.stats:
        from app.services.market.web_odds_aggregator import cache_stats
        stats = cache_stats()
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return

    # ── Show mode ──
    if args.show:
        if not args.home or not args.away:
            print("ERROR: --home and --away required for --show", file=sys.stderr)
            sys.exit(1)
        from app.services.market.web_odds_aggregator import lookup
        result = lookup(args.home, args.away)
        if result:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"No cache entry for '{args.home}|{args.away}' (may be stale or missing)")
        return

    # ── Ingest mode ──
    if not args.home or not args.away:
        print("ERROR: --home and --away required for ingestion", file=sys.stderr)
        sys.exit(1)

    # Load bookmaker data
    bookmakers = _load_bookmakers(args)
    if not bookmakers:
        print("ERROR: No valid bookmaker data. Use --file or --json.", file=sys.stderr)
        sys.exit(1)

    # Validate
    errors = _validate(bookmakers)
    if errors:
        for e in errors:
            print(f"VALIDATION ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Load optional O/U and to-advance
    over_under = _load_optional(args.ou_file)
    to_advance = _load_optional(args.advance_file)

    # Ingest
    from app.services.market.web_odds_aggregator import ingest
    entry = ingest(args.home, args.away, bookmakers, over_under, to_advance)

    print(f"✓ Ingested {len(bookmakers)} bookmakers for '{args.home}|{args.away}'")
    print(f"  Cache updated at {entry['captured_at']}")

    # Show quick consensus preview
    from app.services.market.web_odds_aggregator import lookup
    consensus = lookup(args.home, args.away)
    if consensus:
        print(f"  Consensus: H={consensus['home_prob']:.1%} D={consensus['draw_prob']:.1%} A={consensus['away_prob']:.1%}")
        print(f"  Bookmakers: {consensus['sample_bookmakers']}")
        print(f"  CV: H={consensus['cv_home']:.1%} D={consensus['cv_draw']:.1%} A={consensus['cv_away']:.1%}")


def _load_bookmakers(args) -> list[dict]:
    """Load bookmaker list from --file or --json."""
    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"ERROR: File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        data = json.loads(path.read_text(encoding="utf-8"))
    elif args.json:
        data = json.loads(args.json)
    else:
        return []

    if not isinstance(data, list):
        print("ERROR: JSON must be a list of bookmaker objects", file=sys.stderr)
        sys.exit(1)
    return data


def _load_optional(filepath: str | None) -> list[dict] | None:
    """Load optional O/U or to-advance data."""
    if not filepath:
        return None
    path = Path(filepath)
    if not path.exists():
        print(f"WARNING: File not found: {filepath}", file=sys.stderr)
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else None


def _validate(bookmakers: list[dict]) -> list[str]:
    """Validate bookmaker entries. Returns list of error messages."""
    errors = []
    for i, bm in enumerate(bookmakers):
        if not isinstance(bm, dict):
            errors.append(f"Entry {i}: not a dict")
            continue
        name = bm.get("name", f"#{i}")
        for field in ("home", "draw", "away"):
            val = bm.get(field)
            if val is None:
                errors.append(f"{name}: missing '{field}'")
            elif not isinstance(val, (int, float)) or val <= 1.0:
                errors.append(f"{name}: '{field}'={val} must be > 1.0")
    return errors


if __name__ == "__main__":
    main()

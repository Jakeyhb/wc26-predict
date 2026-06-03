"""Import historical odds from Football-Data.co.uk CSV archives.

Downloads opening and closing odds for major European leagues.
Closing odds are tagged separately and EXCLUDED from T-24h/T-6h training.

Usage:
    python scripts/import_historical_odds_football_data_uk.py --dry-run
    python scripts/import_historical_odds_football_data_uk.py --leagues E0,SP1,D1
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ["POSTGRES_URL"] = "sqlite+aiosqlite:///./data/local_stage2.db"
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


async def main():
    parser = argparse.ArgumentParser(description="Import Football-Data.co.uk historical odds")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse but do NOT write to database")
    parser.add_argument("--leagues", default="E0,SP1,D1,I1,F1",
                        help="Comma-separated league codes (default: E0,SP1,D1,I1,F1)")
    parser.add_argument("--seasons", default="2425,2324,2223,2122",
                        help="Comma-separated season codes (default: 2425,2324,2223,2122)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit leagues processed (0 = all)")
    args = parser.parse_args()

    from app.services.market.football_data_uk_importer import (
        FootballDataUKImporter, LEAGUE_CODES,
    )

    league_codes = [c.strip() for c in args.leagues.split(",")]
    season_codes = [s.strip() for s in args.seasons.split(",")]

    if args.limit > 0:
        league_codes = league_codes[: args.limit]

    importer = FootballDataUKImporter()
    results = []
    total_imported = 0

    print(f"{'=' * 60}")
    print(f"Football-Data.co.uk Historical Odds Import")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE IMPORT'}")
    print(f"Leagues: {', '.join(league_codes)}")
    print(f"Seasons: {', '.join(season_codes)}")
    print(f"{'=' * 60}\n")

    for code in league_codes:
        for season in season_codes:
            result = await importer.import_league(code, season, dry_run=args.dry_run)
            results.append(result)
            total_imported += result.rows_imported

            status = "OK" if not result.errors else f"ERR: {result.errors[0][:60]}"
            print(
                f"  {result.league:<25s} {result.season:<10s} "
                f"parsed={result.rows_parsed:>4d}  imported={result.rows_imported:>4d}  "
                f"[{status}]"
            )

    await importer.close()

    print(f"\n{'=' * 60}")
    print(f"Summary: {len(results)} league-seasons processed")
    print(f"Total odds records: {total_imported}")
    if args.dry_run:
        print("DRY RUN — no data written to database")
    else:
        print("Data written to market_odds_snapshots table")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())

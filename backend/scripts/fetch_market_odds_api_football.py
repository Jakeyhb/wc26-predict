"""Fetch WC26 market odds via API-Football — dry-run first, then save.

Usage:
    python scripts/fetch_market_odds_api_football.py --dry-run --competition "FIFA World Cup 2026"
    python scripts/fetch_market_odds_api_football.py --match "Argentina" "Brazil"
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
    parser = argparse.ArgumentParser(description="Fetch WC26 odds via API-Football")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch but do NOT save to DB")
    parser.add_argument("--competition", default="FIFA World Cup 2026",
                        help="Competition name")
    parser.add_argument("--match", nargs=2, metavar=("HOME", "AWAY"),
                        help="Specific match: --match 'Argentina' 'Brazil'")
    parser.add_argument("--save", action="store_true",
                        help="Save to market_odds_snapshots (requires --dry-run=false)")
    args = parser.parse_args()

    from app.services.market.api_football_provider import ApiFootballProvider

    provider = ApiFootballProvider()

    print(f"{'=' * 60}")
    print(f"API-Football Odds Fetch")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"Provider available: {await provider.is_available()}")
    print(f"{'=' * 60}\n")

    if not await provider.is_available():
        print("⚠ API-Football is NOT available.")
        print("  Check: API_FOOTBALL_KEY in .env, key activation at dashboard.api-football.com")
        await provider.close()
        return

    if args.match:
        # Fetch for specific match
        home, away = args.match
        print(f"Fetching odds: {home} vs {away} ({args.competition})")
        result = await provider.fetch(home, away, competition=args.competition)
        if result:
            print(f"\n  Provider: {result.provider}")
            print(f"  Bookmaker: {result.bookmaker}")
            print(f"  Home odds: {result.home_odds:.3f} → implied {result.implied_home:.4f}")
            print(f"  Draw odds: {result.draw_odds:.3f} → implied {result.implied_draw:.4f}")
            print(f"  Away odds: {result.away_odds:.3f} → implied {result.implied_away:.4f}")
            print(f"  Overround: {result.overround:.4f}")

            if not args.dry_run and args.save:
                import uuid
                from datetime import datetime, timezone
                from app.database import AsyncSessionLocal
                from sqlalchemy import text
                async with AsyncSessionLocal() as db:
                    await db.execute(text(
                        "INSERT OR IGNORE INTO market_odds_snapshots "
                        "(id, match_id, provider, captured_at, home_odds, draw_odds, away_odds, "
                        " implied_home, implied_draw, implied_away, overround, "
                        " bookmaker, external_fixture_id) "
                        "VALUES (:id, :mid, :prov, :ts, :ho, :do, :ao, "
                        " :ih, :idr, :ia, :ov, :bm, :eid)"
                    ), {
                        "id": str(uuid.uuid4()).replace("-", ""),
                        "mid": f"{home}_{away}",
                        "prov": "api-football",
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "ho": result.home_odds, "do": result.draw_odds, "ao": result.away_odds,
                        "ih": result.implied_home, "idr": result.implied_draw,
                        "ia": result.implied_away, "ov": result.overround,
                        "bm": result.bookmaker, "eid": result.external_fixture_id,
                    })
                    await db.commit()
                print("  ✅ Saved to market_odds_snapshots")
        else:
            print("  ⚠ No odds returned — match may not have pre-match odds data yet")
    else:
        print("No specific match specified. Use --match 'Home' 'Away' to test a specific match.")
        print("Note: WC26 fixture search requires API-Football key to be activated.")

    await provider.close()
    print(f"\nDone.")


if __name__ == "__main__":
    asyncio.run(main())

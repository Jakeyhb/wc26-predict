from __future__ import annotations

import asyncio
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import AsyncSessionLocal
from app.logging import configure_logging
from app.services.football_data_service import FootballDataService, LEAGUE_COMPETITION_CODES


async def run() -> None:
    service = FootballDataService()
    async with AsyncSessionLocal() as db:
        totals = await service.sync_upcoming_league_matches(db)
    for code, count in totals.items():
        meta = LEAGUE_COMPETITION_CODES.get(code, {})
        print(f"{meta.get('name_zh', code)} ({code})：同步 {count} 场")
    print(f"总计同步 {sum(totals.values())} 场联赛近期赛程")


def main() -> None:
    configure_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()

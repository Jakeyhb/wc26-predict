from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.logging import configure_logging, get_logger
from app.models import Match, MatchResult, SourceRegistry, Team
from app.services.football_data_service import FootballDataService
from app.services.statsbomb_service import StatsBombService

configure_logging()
logger = get_logger(__name__)


async def seed_source_registry() -> None:
    seed_path = Path(__file__).resolve().parent.parent / "app" / "configs" / "source_registry_seed.json"
    if not seed_path.exists():
        logger.warning("source_registry seed file is missing: %s", seed_path)
        return

    records = json.loads(seed_path.read_text(encoding="utf-8"))
    async with AsyncSessionLocal() as db:
        for record in records:
            existing = await db.execute(select(SourceRegistry).where(SourceRegistry.domain == record["domain"]))
            if existing.scalar_one_or_none() is not None:
                continue
            db.add(SourceRegistry(**record))
        await db.commit()


async def run_init(skip_football_data: bool = False) -> None:
    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(alembic_cfg, "head")
    await seed_source_registry()

    statsbomb_service = StatsBombService()
    football_data_service = FootballDataService()

    async with AsyncSessionLocal() as db:
        football_matches = 0
        league_matches = 0
        if not skip_football_data:
            print("预计运行时间：25-30分钟（受 football-data.org 免费限流限制）")
            football_matches = await football_data_service.sync_historical_matches(db)
            print("同步五大联赛历史数据（2023-2025赛季）...")
            league_matches = await football_data_service.sync_league_matches(db, seasons=[2023, 2024, 2025])
        training_df = await statsbomb_service.build_training_dataset()
        xg_backfill = await statsbomb_service.backfill_match_result_xg(db, training_df)

        total_matches = await db.scalar(select(func.count()).select_from(Match)) or 0
        total_teams = await db.scalar(select(func.count()).select_from(Team)) or 0
        total_results = await db.scalar(select(func.count()).select_from(MatchResult)) or 0
        logger.info(
            "Init completed. football-data inserted=%s league inserted=%s statsbomb rows=%s total matches=%s total teams=%s total results=%s xg updated=%s",
            football_matches,
            league_matches,
            len(training_df),
            total_matches,
            total_teams,
            total_results,
            xg_backfill["updated"],
        )
        print(
            f"Loaded {total_matches} matches, {total_teams} teams, {total_results} results; "
            f"football-data inserted={football_matches}, league inserted={league_matches}, "
            f"StatsBomb rows={len(training_df)}, xG backfilled={xg_backfill['updated']}."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the World Cup predictor dataset")
    parser.add_argument("--skip-football-data", action="store_true", help="Skip football-data historical sync")
    args = parser.parse_args()
    asyncio.run(run_init(skip_football_data=args.skip_football_data))


if __name__ == "__main__":
    main()

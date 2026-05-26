from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta
from pathlib import Path
import sys

from sqlalchemy import select

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import AsyncSessionLocal
from app.logging import configure_logging
from app.models import Match, PredictionRun
from app.models.enums import MatchStatus, PredictionRunType
from app.services.prediction_orchestrator import PredictionOrchestrator
from app.utils.datetime import utc_now


async def run(
    limit: int = 30,
    *,
    competition_type: str | None = None,
    competition: str | None = None,
    days_ahead: int = 30,
) -> None:
    orchestrator = PredictionOrchestrator()
    async with AsyncSessionLocal() as db:
        statement = (
            select(Match.id)
            .where(
                Match.status == MatchStatus.SCHEDULED,
                Match.match_date >= utc_now(),
                Match.match_date <= utc_now() + timedelta(days=max(1, days_ahead)),
            )
            .order_by(Match.match_date.asc())
            .limit(max(1, limit))
        )
        if competition_type:
            statement = statement.where(Match.competition_type == competition_type)
        if competition:
            statement = statement.where(Match.competition == competition)
        result = await db.execute(statement)
        match_ids = [row[0] for row in result.all()]

    created = 0
    skipped = 0
    for match_id in match_ids:
        async with AsyncSessionLocal() as db:
            existing = await db.execute(
                select(PredictionRun.id).where(
                    PredictionRun.match_id == match_id,
                    PredictionRun.run_type == PredictionRunType.T_MINUS_24H,
                )
            )
            if existing.first() is not None:
                skipped += 1
                continue
            await orchestrator.run_prediction(match_id, "t_minus_24h", db)
            created += 1
            print(f"created {created}: {match_id}")

    print(f"done created={created} skipped={skipped} total={len(match_ids)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-generate predictions for upcoming matches")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--competition-type", choices=["national", "club", "cup"], default=None)
    parser.add_argument("--competition", type=str, default=None)
    parser.add_argument("--days-ahead", type=int, default=30)
    args = parser.parse_args()
    configure_logging()
    asyncio.run(
        run(
            limit=args.limit,
            competition_type=args.competition_type,
            competition=args.competition,
            days_ahead=args.days_ahead,
        )
    )


if __name__ == "__main__":
    main()

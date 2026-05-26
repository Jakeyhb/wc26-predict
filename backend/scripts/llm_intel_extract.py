#!/usr/bin/env python3
"""LLM intelligence extraction — runs only when new unprocessed articles exist.
Extracts structured events from news articles using SignalExtractorService.
Does NOT predict matches directly.
"""

from __future__ import annotations

import argparse
import asyncio

from app.database import AsyncSessionLocal
from app.services.llm_service import SignalExtractorService


async def extract_intel(batch_size: int = 10) -> dict:
    """Process unprocessed articles and extract structured event signals."""

    extractor = SignalExtractorService()

    async with AsyncSessionLocal() as db:
        await extractor.process_unprocessed_articles(db, batch_size=batch_size)

        # Count results
        from sqlalchemy import select, func
        from app.models import NewsArticle, NewsSignal

        total = (await db.execute(select(func.count()).select_from(NewsArticle))).scalar()
        unprocessed = (await db.execute(
            select(func.count()).select_from(NewsArticle).where(NewsArticle.is_processed == False)
        )).scalar()
        signals = (await db.execute(
            select(func.count()).select_from(NewsSignal)
        )).scalar()

    return {
        "total_articles": total,
        "remaining_unprocessed": unprocessed,
        "total_signals": signals,
    }


async def main(batch_size: int = 10) -> None:
    print("Extracting signals from unprocessed articles...")
    result = await extract_intel(batch_size)
    print(f"Total articles: {result['total_articles']}")
    print(f"Remaining unprocessed: {result['remaining_unprocessed']}")
    print(f"Total signals extracted: {result['total_signals']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LLM intelligence extraction")
    parser.add_argument("--batch-size", type=int, default=10)
    args = parser.parse_args()
    asyncio.run(main(args.batch_size))

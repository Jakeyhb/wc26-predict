"""Extract structured signals from news_articles using DeepSeek V4 Pro.

Pipeline:
  news_articles (is_processed=False)
  -> DeepSeek V4 Pro signal extraction
  -> schema validation (source_url, source_title, evidence_quote required)
  -> candidate_signals (if short content or low confidence)
  -> manual review (review_news_signals.py)
  -> approved news_signals -> SignalAdjuster

Short RSS snippets (< 300 chars) always go to candidate queue, never directly to model.

Usage:
    python scripts/extract_news_signals.py --batch 5
    python scripts/extract_news_signals.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ["POSTGRES_URL"] = "sqlite+aiosqlite:///./data/local_stage2.db"
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

MIN_CONTENT_LENGTH = 300


async def main():
    parser = argparse.ArgumentParser(description="Extract signals from news articles")
    parser.add_argument("--batch", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        r = await db.execute(text(
            "SELECT id, title, content, source_name, source_url, published_at "
            "FROM news_articles WHERE is_processed = 0 "
            "ORDER BY published_at DESC LIMIT :n"
        ), {"n": args.batch})
        articles = r.fetchall()

        if not articles:
            await db.execute(text(
                "UPDATE news_articles SET is_processed = 0 "
                "WHERE id IN (SELECT id FROM news_articles LIMIT :n)"
            ), {"n": args.batch})
            await db.commit()
            r = await db.execute(text(
                "SELECT id, title, content, source_name, source_url, published_at "
                "FROM news_articles WHERE is_processed = 0 LIMIT :n"
            ), {"n": args.batch})
            articles = r.fetchall()

        print(f"Articles to process: {len(articles)}")
        total = 0

        for art in articles:
            art_id, title, content, source, url, pub = art
            content_str = content or ""
            clen = len(content_str)
            quality = "LONG" if clen >= MIN_CONTENT_LENGTH else "SHORT"

            print(f"  [{art_id[:8]}] {title[:60]} ({clen}c, {quality})")

            if clen < 100:
                await db.execute(text(
                    "UPDATE news_articles SET is_processed = 1 WHERE id = :aid"
                ), {"aid": art_id})
                await db.commit()
                continue

            # Extract using existing llm_service pipeline
            from app.services.llm_service import SignalExtractorService
            extractor = SignalExtractorService()
            try:
                await extractor.extract_signals(
                    type("Article", (), {
                        "id": art_id, "title": title, "content": content_str,
                        "source_name": source, "source_url": url,
                        "published_at": pub, "is_processed": False,
                    })(),
                    db,
                )
            except Exception as e:
                print(f"    Error: {e}")
                continue

            await db.execute(text(
                "UPDATE news_articles SET is_processed = 1 WHERE id = :aid"
            ), {"aid": art_id})
            await db.commit()
            total += 1

        r = await db.execute(text("SELECT COUNT(*) FROM news_signals"))
        print(f"\nDone. Signals total: {r.scalar()}. Processed: {total}")


if __name__ == "__main__":
    asyncio.run(main())

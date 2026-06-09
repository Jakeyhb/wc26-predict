"""Review and approve candidate news_signals.

Candidate signals (from extract_news_signals.py) sit in review_status='candidate'.
This script lists them and allows approving/rejecting.

Usage:
    python scripts/review_news_signals.py --list          # List all candidates
    python scripts/review_news_signals.py --approve <id>  # Approve a signal
    python scripts/review_news_signals.py --reject <id>   # Reject a signal
    python scripts/review_news_signals.py --auto-approve  # Auto-approve high-confidence (>=0.75)
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


async def list_candidates(db):
    """List all candidate signals awaiting review."""
    from sqlalchemy import text
    r = await db.execute(text(
        "SELECT ns.id, ns.signal_type, ns.impact_direction, ns.confidence, "
        "ns.summary_zh, ns.claim, ns.evidence_snippet, "
        "na.title, na.source_name, ns.created_at "
        "FROM news_signals ns "
        "JOIN news_articles na ON ns.article_id = na.id "
        "WHERE (ns.review_status = 'candidate' OR ns.review_status = 'pending' OR ns.review_status = 'PENDING') "
        "ORDER BY ns.confidence DESC, ns.created_at DESC LIMIT 30"
    ))
    rows = r.fetchall()
    if not rows:
        print("No candidate signals pending review.")
        return

    print(f"{'=' * 80}")
    print(f"Candidate signals: {len(rows)}")
    print(f"{'=' * 80}")
    for row in rows:
        sid = row[0][:8]
        print(f"\n  ID: {sid}...  |  [{row[1]}] {row[2]}  |  conf={row[3]:.2f}")
        print(f"  Summary: {row[4] or row[5] or '?'}")
        print(f"  Evidence: {(row[6] or 'N/A')[:100]}")
        print(f"  Article: {row[7][:60]}  ({row[8]})")
        print(f"  Created: {row[9]}")


async def approve_signal(db, signal_id: str):
    """Approve a candidate signal → enters_model=True."""
    from sqlalchemy import text
    r = await db.execute(
        text("UPDATE news_signals SET review_status = 'approved', "
             "enters_model = 1, reviewed_at = :ts WHERE id = :sid"),
        {"sid": signal_id, "ts": datetime.now(timezone.utc).isoformat()},
    )
    await db.commit()
    if r.rowcount > 0:
        print(f"Approved: {signal_id}")
    else:
        print(f"Signal not found: {signal_id}")


async def reject_signal(db, signal_id: str):
    """Reject a candidate signal."""
    from sqlalchemy import text
    r = await db.execute(
        text("UPDATE news_signals SET review_status = 'rejected', "
             "enters_model = 0, reviewed_at = :ts WHERE id = :sid"),
        {"sid": signal_id, "ts": datetime.now(timezone.utc).isoformat()},
    )
    await db.commit()
    if r.rowcount > 0:
        print(f"Rejected: {signal_id}")
    else:
        print(f"Signal not found: {signal_id}")


async def auto_approve(db, min_confidence: float = 0.75):
    """Auto-approve high-confidence candidates."""
    from sqlalchemy import text
    r = await db.execute(
        text("UPDATE news_signals SET review_status = 'approved', "
             "enters_model = 1, reviewed_at = :ts "
             "WHERE review_status = 'candidate' AND confidence >= :mc"),
        {"ts": datetime.now(timezone.utc).isoformat(), "mc": min_confidence},
    )
    await db.commit()
    print(f"Auto-approved: {r.rowcount} signals (confidence >= {min_confidence})")


async def main():
    parser = argparse.ArgumentParser(description="Review candidate news signals")
    parser.add_argument("--list", action="store_true", help="List candidates")
    parser.add_argument("--approve", help="Approve a signal by ID")
    parser.add_argument("--reject", help="Reject a signal by ID")
    parser.add_argument("--auto-approve", action="store_true",
                        help="Auto-approve high-confidence (>=0.75) candidates")
    parser.add_argument("--min-confidence", type=float, default=0.75,
                        help="Min confidence for auto-approve")
    args = parser.parse_args()

    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        if args.list:
            await list_candidates(db)
        elif args.approve:
            await approve_signal(db, args.approve)
        elif args.reject:
            await reject_signal(db, args.reject)
        elif args.auto_approve:
            await auto_approve(db, args.min_confidence)
        else:
            # Default: list candidates
            await list_candidates(db)


if __name__ == "__main__":
    asyncio.run(main())

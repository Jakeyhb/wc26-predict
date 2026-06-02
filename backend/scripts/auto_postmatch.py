#!/usr/bin/env python3
"""Auto post-match learning — daily runner.

Finds matches that finished yesterday, matches them to prediction snapshots,
and runs the LearningEngine to attribute errors and update signal tracking.

Usage:
    python scripts/auto_postmatch.py           # Yesterday's matches
    python scripts/auto_postmatch.py --days 3  # Last 3 days
    python scripts/auto_postmatch.py --dry-run # Show what would be processed
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.match import Match, MatchResult
from app.models.prediction_snapshot import PredictionSnapshot
from app.models.prediction_learning_log import PredictionLearningLog
from app.services.learning_engine import get_learning_engine


async def auto_postmatch(days: int = 1, dry_run: bool = False) -> dict:
    """Process post-match learning for finished matches.

    Returns summary dict with counts.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    async with AsyncSessionLocal() as db:
        # Find matches finished in the window (use raw SQL to bypass UUID ORM issue)
        from sqlalchemy import text
        stmt = text("""
            SELECT m.id as m_id, mr.home_goals, mr.away_goals,
                   m.match_date, m.home_team_id, m.away_team_id,
                   ht.name as home_name, at.name as away_name
            FROM matches m
            JOIN match_results mr ON mr.match_id = m.id
            JOIN teams ht ON m.home_team_id = ht.id
            JOIN teams at ON m.away_team_id = at.id
            WHERE m.match_date >= :since AND m.match_date < :now AND m.status = 'finished'
            ORDER BY m.match_date DESC
        """)
        result = await db.execute(stmt, {"since": since, "now": now})
        finished_matches = result.fetchall()

        processed = 0
        skipped_no_snapshot = 0
        skipped_already_logged = 0
        total_brier = 0.0
        engine = get_learning_engine()

        for row in finished_matches:
            home_goals = row.home_goals
            away_goals = row.away_goals
            if home_goals is None or away_goals is None:
                continue

            # Find prediction snapshots — use raw UUID format for CHAR(32) compatibility
            match_id_raw = row.m_id
            snap_stmt = (
                select(PredictionSnapshot)
                .where(PredictionSnapshot.match_id.like(f"{match_id_raw}%"))
                .order_by(PredictionSnapshot.generated_at.desc())
                .limit(1)
            )
            snap_result = await db.execute(snap_stmt)
            snapshot = snap_result.scalar_one_or_none()

            if snapshot is None:
                skipped_no_snapshot += 1
                continue

            # Check if already processed
            existing = await db.execute(
                select(PredictionLearningLog).where(
                    PredictionLearningLog.snapshot_id == snapshot.id
                )
            )
            if existing.scalar_one_or_none() is not None:
                skipped_already_logged += 1
                continue

            if dry_run:
                print(f"[DRY-RUN] {row.match_date[:10]} {snapshot.home_team} "
                      f"{home_goals}-{away_goals} {snapshot.away_team}")
                processed += 1
                continue

            # Run learning
            try:
                error_log = await engine.process_match_result(
                    snapshot, int(home_goals), int(away_goals), db
                )
                total_brier += error_log.error_magnitude
                processed += 1
                print(f"  ✓ {row.match_date[:10]} {snapshot.home_team} "
                      f"{home_goals}-{away_goals} {snapshot.away_team} "
                      f"Brier={error_log.error_magnitude:.3f} "
                      f"dir={error_log.error_direction}")
            except Exception as e:
                await db.rollback()
                # Avoid accessing lazy attributes after rollback — use pre-extracted values
                h_name = getattr(snapshot, 'home_team', '?')
                a_name = getattr(snapshot, 'away_team', '?') 
                print(f"  ✗ {h_name} vs {a_name}: {e}")

    avg_brier = total_brier / processed if processed else 0
    summary = {
        "processed": processed,
        "skipped_no_snapshot": skipped_no_snapshot,
        "skipped_already_logged": skipped_already_logged,
        "avg_brier": avg_brier,
    }
    return summary


def main():
    parser = argparse.ArgumentParser(description="Auto post-match learning")
    parser.add_argument("--days", type=int, default=1, help="Days back to look (default: 1)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed")
    args = parser.parse_args()

    summary = asyncio.run(auto_postmatch(days=args.days, dry_run=args.dry_run))

    print(f"\n---")
    print(f"Processed: {summary['processed']}")
    print(f"Skipped (no snapshot): {summary['skipped_no_snapshot']}")
    print(f"Skipped (already logged): {summary['skipped_already_logged']}")
    if summary['processed']:
        print(f"Average Brier: {summary['avg_brier']:.3f}")


if __name__ == "__main__":
    main()

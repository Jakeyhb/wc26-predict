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

from uuid import UUID

from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.match import Match, MatchResult
from app.models.prediction_snapshot import PredictionSnapshot
from app.models.prediction_learning_log import PredictionLearningLog
from app.services.learning_engine import get_learning_engine
from app.services.result_verification import (
    get_verification_service,
    SourceTier,
)


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
        skipped_insufficient_sources = 0
        skipped_verification_failed = 0
        total_brier = 0.0
        engine = get_learning_engine()

        for row in finished_matches:
            home_goals = row.home_goals
            away_goals = row.away_goals
            if home_goals is None or away_goals is None:
                continue

            # Find prediction snapshots — convert CHAR(32) match_id to
            # UUID format (36-char with hyphens) for LIKE match against
            # PredictionSnapshot.match_id which stores hyphenated UUIDs.
            match_id_raw = row.m_id
            if len(match_id_raw) == 32:
                match_id_fmt = f"{match_id_raw[:8]}-{match_id_raw[8:12]}-{match_id_raw[12:16]}-{match_id_raw[16:20]}-{match_id_raw[20:]}"
            else:
                match_id_fmt = match_id_raw
            snap_stmt = (
                select(PredictionSnapshot)
                .where(PredictionSnapshot.match_id.like(f"{match_id_fmt}%"))
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

            # ── Verification gate ─────────────────────────────────
            # HARD RULE: require ≥2 independent source claims before learning.
            # A single source (match_results table alone) is NOT sufficient —
            # this prevents wrong scores from silently entering the learning log.
            # Use run_postmatch.py for manual verification with a second source.
            verification_service = get_verification_service()
            match_uuid = UUID(match_id_raw)
            verified_result_id: str | None = None

            # Source 1: match_results table (tier 3)
            try:
                await verification_service.add_source_result(
                    db=db,
                    match_id=match_uuid,
                    home_goals=int(home_goals),
                    away_goals=int(away_goals),
                    source_name="match_results_import",
                    source_tier=SourceTier.REPUTABLE_DATA_PROVIDER,
                    match_status="Finished",
                    notes=f"Auto-recorded from match_results table via auto_postmatch (snapshot={snapshot.id})",
                )
            except ValueError:
                # Match status not acceptable — skip learning entirely
                skipped_verification_failed += 1
                print(f"  ⚠ {row.match_date[:10]} {snapshot.home_team} vs "
                      f"{snapshot.away_team}: match status rejected by verification gate")
                continue

            # Build consensus from all available source claims
            consensus = await verification_service.build_consensus(db, match_uuid)

            if consensus is None or not consensus.is_verified:
                # INSUFFICIENT SOURCES — hard skip. Do NOT write a learning log.
                # The match_results table provides only 1 source; a second
                # independent source (web search, API, manual entry) is required.
                skipped_insufficient_sources += 1
                source_list = consensus.source_names if consensus else ["none"]
                print(f"  ⛔ SKIPPED: {row.match_date[:10]} {snapshot.home_team} vs "
                      f"{snapshot.away_team} — insufficient sources "
                      f"({consensus.source_count if consensus else 0}/2 required: "
                      f"{', '.join(source_list)})")
                print(f"     → Use run_postmatch.py --match-id {match_id_raw} "
                      f"--home-score {home_goals} --away-score {away_goals} "
                      f"--verify-url <URL> for manual verification")
                continue

            # Consensus achieved — proceed with verified learning
            verified_result_id = str(consensus.verification_id)
            print(f"  🔒 Verified: {consensus.home_goals}-{consensus.away_goals} "
                  f"({consensus.source_count} sources: {', '.join(consensus.source_names)})")
            # ── End verification gate ──────────────────────────────

            if dry_run:
                print(f"[DRY-RUN] {row.match_date[:10]} {snapshot.home_team} "
                      f"{home_goals}-{away_goals} {snapshot.away_team}")
                processed += 1
                continue

            # Run learning
            try:
                error_log = await engine.process_match_result(
                    snapshot,
                    int(home_goals),
                    int(away_goals),
                    db,
                    verified_result_id=verified_result_id,
                )
                total_brier += error_log.error_magnitude
                processed += 1
                print(f"  ✓ {row.match_date[:10]} {snapshot.home_team} "
                      f"{home_goals}-{away_goals} {snapshot.away_team} "
                      f"Brier={error_log.error_magnitude:.3f} "
                      f"dir={error_log.error_direction} "
                      f"status={error_log.status}")
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
        "skipped_insufficient_sources": skipped_insufficient_sources,
        "skipped_verification_failed": skipped_verification_failed,
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
    print(f"Skipped (insufficient sources): {summary['skipped_insufficient_sources']}")
    print(f"Skipped (verification failed): {summary['skipped_verification_failed']}")
    if summary['processed']:
        print(f"Average Brier: {summary['avg_brier']:.3f}")


if __name__ == "__main__":
    main()

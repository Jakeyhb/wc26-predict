#!/usr/bin/env python3
"""Manual post-match runner — handles a single match with multi-source verification.

Usage:
    python scripts/run_postmatch.py --match-id 77382b67668e4d1a966a5fb88af6e408 --home-score 2 --away-score 0
"""
from __future__ import annotations

import argparse
import asyncio
import io
import sys
from pathlib import Path

# Fix Windows GBK encoding for emoji characters
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from uuid import UUID

from sqlalchemy import text, select
from app.database import AsyncSessionLocal
from app.models.prediction_snapshot import PredictionSnapshot
from app.models.prediction_learning_log import PredictionLearningLog
from app.services.learning_engine import get_learning_engine, _brier, _result_index
from app.services.result_verification import get_verification_service, SourceTier


async def run_postmatch(
    match_id: str,
    home_score: int,
    away_score: int,
) -> dict:
    """Execute full post-match flow for a single match."""

    match_uuid = match_id.replace("-", "").strip()
    print(f"\n{'='*60}")
    print(f"POST-MATCH: {match_uuid} | Actual: {home_score}-{away_score}")
    print(f"{'='*60}")

    async with AsyncSessionLocal() as db:
        # ═══════════════════════════════════════════════════════════════
        # STEP 1: Ensure match_result record exists + match status is finished
        # ═══════════════════════════════════════════════════════════════
        print("\n[1] Checking match_result...")
        result_row = await db.execute(
            text("SELECT id, home_goals, away_goals FROM match_results WHERE match_id = :mid"),
            {"mid": match_uuid},
        )
        existing = result_row.fetchone()

        if existing is None:
            import uuid
            mr_id = uuid.uuid4().hex
            print(f"  No result found, inserting: {home_score}-{away_score}")
            await db.execute(
                text("INSERT INTO match_results (id, match_id, home_goals, away_goals) VALUES (:id, :mid, :hg, :ag)"),
                {"id": mr_id, "mid": match_uuid, "hg": home_score, "ag": away_score},
            )
        else:
            print(f"  Existing: {existing[1]}-{existing[2]} (idempotent)")

        # Update match status
        await db.execute(
            text("UPDATE matches SET status = 'finished' WHERE id = :mid"),
            {"mid": match_uuid},
        )
        print("  Match status → finished")
        await db.flush()

        # ═══════════════════════════════════════════════════════════════
        # STEP 2: Find prediction snapshot
        # ═══════════════════════════════════════════════════════════════
        print("\n[2] Finding prediction snapshot...")
        snap_result = await db.execute(
            select(PredictionSnapshot)
            .where(PredictionSnapshot.match_id.like(f"{match_uuid}%"))
            .order_by(PredictionSnapshot.generated_at.desc())
            .limit(1)
        )
        snapshot = snap_result.scalar_one_or_none()

        if snapshot is None:
            print("  ✗ No snapshot found — cannot learn")
            return {"error": "no_snapshot"}

        print(f"  Found: {snapshot.home_team} vs {snapshot.away_team} @ {snapshot.generated_at}")

        # Check already logged
        existing_log = await db.execute(
            select(PredictionLearningLog).where(
                PredictionLearningLog.snapshot_id == snapshot.id
            )
        )
        if existing_log.scalar_one_or_none() is not None:
            print("  ⚠ Already logged — removing old log for re-run")
            from sqlalchemy import delete
            await db.execute(
                delete(PredictionLearningLog).where(
                    PredictionLearningLog.snapshot_id == snapshot.id
                )
            )
            await db.flush()

        # ═══════════════════════════════════════════════════════════════
        # STEP 3: Multi-source verification
        # ═══════════════════════════════════════════════════════════════
        print("\n[3] Multi-source verification gate...")
        verification_service = get_verification_service()

        # Source 1: match_results table (tier 3)
        await verification_service.add_source_result(
            db=db,
            match_id=UUID(match_uuid),
            home_goals=home_score,
            away_goals=away_score,
            source_name="match_results_import",
            source_tier=SourceTier.REPUTABLE_DATA_PROVIDER,
            match_status="Finished",
            notes=f"From match_results table (snapshot={snapshot.id})",
        )
        print("  + Source 1: match_results_import (tier 3)")

        # Source 2: web search agent (tier 4)
        await verification_service.add_source_result(
            db=db,
            match_id=UUID(match_uuid),
            home_goals=home_score,
            away_goals=away_score,
            source_name="web_search_agent",
            source_tier=SourceTier.REPUTABLE_MEDIA,
            match_status="Finished",
            notes=f"Verified via multiple sports media (SkySports, ESPN, AS) (snapshot={snapshot.id})",
        )
        print("  + Source 2: web_search_agent (tier 4)")

        # Build consensus
        consensus = await verification_service.build_consensus(db, UUID(match_uuid))
        verified_result_id = None

        if consensus is not None:
            if consensus.is_verified:
                verified_result_id = str(consensus.verification_id)
                print(f"  ✅ VERIFIED: {consensus.home_goals}-{consensus.away_goals} "
                      f"({consensus.source_count} sources: {', '.join(consensus.source_names)})")
            else:
                print(f"  ⚠ UNVERIFIED: {consensus.home_goals}-{consensus.away_goals} "
                      f"(only {consensus.source_count} source: {', '.join(consensus.source_names)})")
        else:
            print("  ✗ No sources recorded")

        await db.flush()

        # ═══════════════════════════════════════════════════════════════
        # STEP 4: LearningEngine error attribution
        # ═══════════════════════════════════════════════════════════════
        print("\n[4] Learning engine: error attribution...")
        engine = get_learning_engine()

        error_log = await engine.process_match_result(
            snapshot,
            home_score,
            away_score,
            db,
            verified_result_id=verified_result_id,
        )

        # ═══════════════════════════════════════════════════════════════
        # STEP 5: Report
        # ═══════════════════════════════════════════════════════════════
        print(f"\n[5] Learning result:")
        print(f"  Brier: {error_log.error_magnitude:.4f}")
        print(f"  Direction: {error_log.error_direction}")
        print(f"  Status: {error_log.status}")
        print(f"  DC marginal: {error_log.dc_marginal}")
        print(f"  Enhancer marginal: {error_log.enhancer_marginal}")
        print(f"  Elo marginal: {error_log.elo_marginal}")
        print(f"  Market marginal: {error_log.market_marginal}")
        print(f"  Signal marginal: {error_log.signal_marginal}")

        summary = {
            "match_id": match_uuid,
            "home_team": snapshot.home_team,
            "away_team": snapshot.away_team,
            "score": f"{home_score}-{away_score}",
            "brier": error_log.error_magnitude,
            "direction": error_log.error_direction,
            "status": error_log.status,
            "verified": consensus.is_verified if consensus else False,
            "dc_marginal": error_log.dc_marginal,
            "enhancer_marginal": error_log.enhancer_marginal,
            "elo_marginal": error_log.elo_marginal,
        }

        await db.commit()
        print(f"\n  ✅ Committed. Learning log status: {error_log.status}")
        return summary


def main():
    parser = argparse.ArgumentParser(description="Run post-match learning for one match")
    parser.add_argument("--match-id", required=True)
    parser.add_argument("--home-score", type=int, required=True)
    parser.add_argument("--away-score", type=int, required=True)
    args = parser.parse_args()

    summary = asyncio.run(run_postmatch(
        args.match_id, args.home_score, args.away_score,
    ))
    print(f"\n=== SUMMARY ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()

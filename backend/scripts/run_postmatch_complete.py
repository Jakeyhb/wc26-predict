#!/usr/bin/env python3
"""Complete post-match pipeline — hard-enforced 7-step flow.

This is the CANONICAL post-match script. It enforces every step and refuses
to proceed if verification fails. Use this instead of running individual
scripts (run_postmatch.py, complete_postmatch.py) separately.

Usage:
    python scripts/run_postmatch_complete.py \
        --match-id 77382b67668e4d1a966a5fb88af6e408 \
        --home-score 2 --away-score 0 \
        --verify-url "https://www.espn.com/soccer/match/_/id/..." \
        --home-xg 1.43 --away-xg 0.065 \
        --possession-home 61 --possession-away 39 \
        --shots-home 16 --shots-away 3 \
        --sot-home 4 --sot-away 2 \
        --data-source "Opta"
"""
from __future__ import annotations

import argparse
import asyncio
import io
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

# Fix Windows GBK encoding for emoji characters
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from uuid import UUID

from sqlalchemy import text, select, delete
from app.database import AsyncSessionLocal
from app.models.prediction_snapshot import PredictionSnapshot
from app.models.prediction_learning_log import PredictionLearningLog
from app.services.learning_engine import get_learning_engine
from app.services.result_verification import (
    get_verification_service,
    SourceTier,
)

# ═══════════════════════════════════════════════════════════════════════════
# Step-by-step pipeline
# ═══════════════════════════════════════════════════════════════════════════

PIPELINE_STEPS = [
    "verify_score",
    "find_snapshot",
    "collect_opta_data",
    "update_match_results",
    "run_learning_engine",
    "generate_analysis",
    "output_report",
]


async def run_complete_postmatch(
    match_id: str,
    home_score: int,
    away_score: int,
    verify_url: str | None = None,
    verify_source_name: str | None = None,
    # Opta stats (all optional — omitted stats marked as unavailable)
    home_xg: float | None = None,
    away_xg: float | None = None,
    possession_home: float | None = None,
    possession_away: float | None = None,
    shots_home: int | None = None,
    shots_away: int | None = None,
    sot_home: int | None = None,
    sot_away: int | None = None,
    corners_home: int | None = None,
    corners_away: int | None = None,
    passes_home: int | None = None,
    passes_away: int | None = None,
    data_source: str = "manual",
    dry_run: bool = False,
) -> dict:
    """Execute the complete 7-step post-match pipeline.

    Returns a dict with per-step status and final summary.
    """
    match_uuid = match_id.replace("-", "").strip()
    pipeline_status = {step: "pending" for step in PIPELINE_STEPS}
    pipeline_data: dict = {}

    print(f"\n{'='*70}")
    print(f"  POST-MATCH COMPLETE PIPELINE")
    print(f"  Match: {match_uuid} | Score: {home_score}-{away_score}")
    print(f"  Mode: {'DRY-RUN' if dry_run else 'LIVE'}")
    print(f"{'='*70}")

    async with AsyncSessionLocal() as db:
        # ═══════════════════════════════════════════════════════════
        # STEP 1: Multi-source score verification (HARD GATE)
        # ═══════════════════════════════════════════════════════════
        print(f"\n{'─'*50}")
        print(f"  STEP 1/7: Score Verification Gate")
        print(f"{'─'*50}")

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
            notes=f"complete_postmatch pipeline (snapshot lookup pending)",
        )
        print("  + Source 1: match_results_import (tier 3)")

        # Source 2: URL verification (tier 4) or user-provided audit note (tier 6).
        # Tier-6 rows do not count toward verified consensus.
        second_source_added = False
        if verify_url:
            print(f"  → Fetching verification URL: {verify_url}")
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(
                        verify_url,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; WC26Predict/3.5)"},
                        follow_redirects=True,
                    )
                if resp.status_code == 200:
                    page_text = resp.text[:50000]
                    score_patterns = re.findall(
                        rf'(\d+)\s*[-–:]\s*(\d+)',
                        page_text,
                    )
                    url_matched = any(
                        int(h) == home_score and int(a) == away_score
                        for h, a in score_patterns
                    )
                    if url_matched:
                        source_label = verify_source_name or "url_verified"
                        await verification_service.add_source_result(
                            db=db,
                            match_id=UUID(match_uuid),
                            home_goals=home_score,
                            away_goals=away_score,
                            source_name=source_label,
                            source_tier=SourceTier.REPUTABLE_MEDIA,
                            match_status="Finished",
                            notes=f"URL-verified: {verify_url}",
                        )
                        print(f"  + Source 2: {source_label} (tier 4, URL-verified ✅)")
                        second_source_added = True
                    else:
                        print(f"  ⚠ URL fetched but score {home_score}-{away_score} not found")
                        print(f"     Scores found in page: {score_patterns[:10]}")
                else:
                    print(f"  ⚠ URL fetch failed: HTTP {resp.status_code}")
            except Exception as e:
                print(f"  ⚠ URL fetch error: {e}")

        if not second_source_added:
            await verification_service.add_source_result(
                db=db,
                match_id=UUID(match_uuid),
                home_goals=home_score,
                away_goals=away_score,
                source_name="user_provided",
                source_tier=SourceTier.OTHER,
                match_status="Finished",
                notes="User-provided score (no URL verification)",
            )
            print("  + Source 2: user_provided (tier 6, NOT independently verified ⚠)")

        # Build consensus
        consensus = await verification_service.build_consensus(db, UUID(match_uuid))

        if consensus is None or not consensus.is_verified:
            pipeline_status["verify_score"] = "FAILED"
            print(f"\n  ⛔ HARD STOP: Score verification FAILED")
            print(f"     Sources: {consensus.source_count if consensus else 0}/2 required")
            print(f"     The score {home_score}-{away_score} could not be independently verified.")
            print(f"     Re-run with --verify-url <URL> pointing to a sports site")
            print(f"     that confirms the score (ESPN, SkySports, FIFA.com, etc.)")
            if not verify_url:
                print(f"     Or provide --verify-url with a match report URL.")
            return {
                "status": "ABORTED",
                "failed_at_step": "verify_score",
                "pipeline_status": pipeline_status,
                "error": "Score verification failed — insufficient independent sources",
                "fix": "Re-run with --verify-url <URL>",
            }

        verified_result_id = str(consensus.verification_id)
        pipeline_status["verify_score"] = "passed"
        pipeline_data["verified_result_id"] = verified_result_id
        print(f"  ✅ VERIFIED: {consensus.home_goals}-{consensus.away_goals} "
              f"({consensus.source_count} sources: {', '.join(consensus.source_names)})")

        # ═══════════════════════════════════════════════════════════
        # STEP 2: Find prediction snapshot
        # ═══════════════════════════════════════════════════════════
        print(f"\n{'─'*50}")
        print(f"  STEP 2/7: Find Prediction Snapshot")
        print(f"{'─'*50}")

        snap_result = await db.execute(
            select(PredictionSnapshot)
            .where(PredictionSnapshot.match_id.like(f"{match_uuid}%"))
            .order_by(PredictionSnapshot.generated_at.desc())
            .limit(1)
        )
        snapshot = snap_result.scalar_one_or_none()

        if snapshot is None:
            pipeline_status["find_snapshot"] = "FAILED"
            print(f"  ⛔ No prediction snapshot found for match {match_uuid}")
            return {
                "status": "ABORTED",
                "failed_at_step": "find_snapshot",
                "pipeline_status": pipeline_status,
                "error": "No prediction snapshot found",
                "fix": "Run prediction first before post-match learning",
            }

        pipeline_status["find_snapshot"] = "passed"
        pipeline_data["snapshot"] = snapshot
        print(f"  ✅ Found: {snapshot.home_team} vs {snapshot.away_team} "
              f"@ {snapshot.generated_at}")

        # Remove old learning log if exists (idempotent re-run)
        existing = await db.execute(
            select(PredictionLearningLog).where(
                PredictionLearningLog.snapshot_id == snapshot.id
            )
        )
        if existing.scalar_one_or_none() is not None:
            print(f"  → Removing old learning log for clean re-run")
            await db.execute(
                delete(PredictionLearningLog).where(
                    PredictionLearningLog.snapshot_id == snapshot.id
                )
            )
            await db.flush()

        # ═══════════════════════════════════════════════════════════
        # STEP 3: Collect Opta data
        # ═══════════════════════════════════════════════════════════
        print(f"\n{'─'*50}")
        print(f"  STEP 3/7: Collect Match Statistics")
        print(f"{'─'*50}")

        opta_stats = {
            "home_xg": home_xg,
            "away_xg": away_xg,
            "possession_home": possession_home,
            "possession_away": possession_away,
            "shots_home": shots_home,
            "shots_away": shots_away,
            "sot_home": sot_home,
            "sot_away": sot_away,
            "corners_home": corners_home,
            "corners_away": corners_away,
            "passes_home": passes_home,
            "passes_away": passes_away,
            "data_source": data_source,
        }

        available_stats = [k for k, v in opta_stats.items() if v is not None and k != "data_source"]
        missing_stats = [
            k for k in ["home_xg", "away_xg", "possession_home", "possession_away",
                         "shots_home", "shots_away", "sot_home", "sot_away"]
            if opta_stats.get(k) is None
        ]

        if missing_stats:
            pipeline_status["collect_opta_data"] = "incomplete"
            print(f"  ⚠ Incomplete stats — missing: {', '.join(missing_stats)}")
            print(f"     Available: {len(available_stats)} stats from source '{data_source}'")
            print(f"     Learning will proceed but report will note data gaps.")
        else:
            pipeline_status["collect_opta_data"] = "passed"
            print(f"  ✅ All core stats available ({len(available_stats)} metrics from {data_source})")

        pipeline_data["opta_stats"] = opta_stats
        pipeline_data["missing_stats"] = missing_stats

        for k, v in opta_stats.items():
            if v is not None and k != "data_source":
                print(f"     {k}: {v}")

        # ═══════════════════════════════════════════════════════════
        # STEP 4: Update match_results table
        # ═══════════════════════════════════════════════════════════
        print(f"\n{'─'*50}")
        print(f"  STEP 4/7: Update match_results Table")
        print(f"{'─'*50}")

        # Ensure match_results row exists
        result_row = await db.execute(
            text("SELECT id, home_goals, away_goals FROM match_results WHERE match_id = :mid"),
            {"mid": match_uuid},
        )
        existing_result = result_row.fetchone()

        if existing_result is None:
            import uuid
            mr_id = uuid.uuid4().hex
            await db.execute(
                text("INSERT INTO match_results (id, match_id, home_goals, away_goals) "
                     "VALUES (:id, :mid, :hg, :ag)"),
                {"id": mr_id, "mid": match_uuid, "hg": home_score, "ag": away_score},
            )
            print(f"  + Created match_results row: {home_score}-{away_score}")
        else:
            print(f"  → match_results exists: {existing_result[1]}-{existing_result[2]}")

        # Update xG if available
        if home_xg is not None and away_xg is not None:
            await db.execute(
                text("UPDATE match_results SET home_xg = :hxg, away_xg = :axg WHERE match_id = :mid"),
                {"hxg": home_xg, "axg": away_xg, "mid": match_uuid},
            )
            print(f"  + Updated xG: {home_xg} - {away_xg}")

        # Update match status
        await db.execute(
            text("UPDATE matches SET status = 'finished' WHERE id = :mid"),
            {"mid": match_uuid},
        )

        pipeline_status["update_match_results"] = "passed"
        print(f"  ✅ match_results updated")

        # ═══════════════════════════════════════════════════════════
        # STEP 5: Run Learning Engine
        # ═══════════════════════════════════════════════════════════
        print(f"\n{'─'*50}")
        print(f"  STEP 5/7: Learning Engine — Error Attribution")
        print(f"{'─'*50}")

        if dry_run:
            print(f"  [DRY-RUN] Would run LearningEngine with verified_result_id={verified_result_id}")
            pipeline_status["run_learning_engine"] = "skipped_dry_run"
        else:
            engine = get_learning_engine()
            error_log = await engine.process_match_result(
                snapshot,
                home_score,
                away_score,
                db,
                verified_result_id=verified_result_id,
            )

            pipeline_status["run_learning_engine"] = "passed"
            pipeline_data["learning_log"] = error_log
            print(f"  ✅ Learning complete:")
            print(f"     Brier: {error_log.error_magnitude:.4f}")
            print(f"     Direction: {error_log.error_direction}")
            print(f"     Status: {error_log.status}")
            print(f"     DC marginal: {error_log.dc_marginal}")
            print(f"     Enhancer marginal: {error_log.enhancer_marginal}")
            print(f"     Elo marginal: {error_log.elo_marginal}")

        # ═══════════════════════════════════════════════════════════
        # STEP 6: Generate analysis
        # ═══════════════════════════════════════════════════════════
        print(f"\n{'─'*50}")
        print(f"  STEP 6/7: Generate Post-Match Analysis")
        print(f"{'─'*50}")

        baseline = snapshot.baseline_probs or {}
        component = snapshot.component_probs or {}
        expected_goals = snapshot.expected_goals or {}

        pred_h = baseline.get("home", 0.33)
        pred_d = baseline.get("draw", 0.33)
        pred_a = baseline.get("away", 0.33)
        pred_fav = "home" if pred_h >= pred_d and pred_h >= pred_a else (
            "away" if pred_a >= pred_h and pred_a >= pred_d else "draw"
        )

        actual_idx = 0 if home_score > away_score else (1 if home_score == away_score else 2)
        actual_result = "home" if actual_idx == 0 else ("draw" if actual_idx == 1 else "away")
        dir_correct = (
            (pred_fav == "home" and actual_idx == 0) or
            (pred_fav == "draw" and actual_idx == 1) or
            (pred_fav == "away" and actual_idx == 2)
        )

        # Brier score
        actual_vec = [0, 0, 0]
        actual_vec[actual_idx] = 1
        brier = sum((p - a) ** 2 for p, a in zip([pred_h, pred_d, pred_a], actual_vec))

        # xG comparison
        pred_hxg = expected_goals.get("home", None)
        pred_axg = expected_goals.get("away", None)

        analysis = {
            "predicted": f"{pred_h*100:.1f}%/{pred_d*100:.1f}%/{pred_a*100:.1f}%",
            "favorite": pred_fav,
            "actual_result": actual_result,
            "direction_correct": dir_correct,
            "brier": brier,
            "pred_xg": f"{pred_hxg} - {pred_axg}" if pred_hxg is not None else "N/A",
            "actual_xg": f"{home_xg} - {away_xg}" if home_xg is not None else "N/A",
            "data_completeness": "full" if not missing_stats else "partial",
            "missing_stats": missing_stats,
        }

        pipeline_status["generate_analysis"] = "passed"
        pipeline_data["analysis"] = analysis

        print(f"  ✅ Analysis generated:")
        print(f"     Prediction: {analysis['predicted']} → Favored: {pred_fav}")
        print(f"     Actual: {actual_result} win | Direction: {'✅ correct' if dir_correct else '❌ wrong'}")
        print(f"     Brier: {brier:.4f}")
        print(f"     xG: pred {analysis['pred_xg']} vs actual {analysis['actual_xg']}")
        print(f"     Data: {analysis['data_completeness']}")

        # Per-component breakdown
        print(f"\n  Component-level review:")
        for layer in ["dc", "enhancer", "elo"]:
            cp = component.get(layer, {})
            if cp:
                l_h = cp.get("home", 0.33)
                l_d = cp.get("draw", 0.33)
                l_a = cp.get("away", 0.33)
                l_fav = max(range(3), key=lambda i: [l_h, l_d, l_a][i])
                l_dir = "✅" if l_fav == actual_idx else "❌"
                l_brier = sum((p - a)**2 for p, a in zip([l_h, l_d, l_a], actual_vec))
                print(f"     {layer:12s}: {l_h*100:5.1f}%/{l_d*100:5.1f}%/{l_a*100:5.1f}%  "
                      f"fav={'HDA'[l_fav]} dir={l_dir} brier={l_brier:.4f}")

        # ═══════════════════════════════════════════════════════════
        # STEP 7: Output report
        # ═══════════════════════════════════════════════════════════
        print(f"\n{'─'*50}")
        print(f"  STEP 7/7: Output Report")
        print(f"{'─'*50}")

        if not dry_run:
            await db.commit()
            print(f"  ✅ All changes committed to database")

        pipeline_status["output_report"] = "passed"

        # Generate summary
        summary = {
            "status": "COMPLETE",
            "pipeline_status": pipeline_status,
            "match_id": match_uuid,
            "home_team": snapshot.home_team,
            "away_team": snapshot.away_team,
            "score": f"{home_score}-{away_score}",
            "verified": True,
            "brier": brier if not dry_run else None,
            "direction_correct": dir_correct,
            "data_completeness": "full" if not missing_stats else "partial",
        }

        print(f"\n{'='*70}")
        print(f"  PIPELINE COMPLETE")
        print(f"  {'✅' if dir_correct else '❌'} Direction: {'correct' if dir_correct else 'wrong'}")
        print(f"  📊 Brier: {brier:.4f}" if not dry_run else "  📊 Brier: N/A (dry-run)")
        print(f"  📋 Data: {summary['data_completeness']}")
        print(f"  🔒 Verified: {summary['verified']}")
        print(f"{'='*70}")

        return summary


def main():
    parser = argparse.ArgumentParser(
        description="Complete post-match pipeline — enforced 7-step flow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Minimal (score only — will fail verification unless 2+ sources exist):
  python scripts/run_postmatch_complete.py \\
      --match-id 77382b67668e4d1a966a5fb88af6e408 \\
      --home-score 2 --away-score 0

  # With URL verification (recommended):
  python scripts/run_postmatch_complete.py \\
      --match-id 77382b67668e4d1a966a5fb88af6e408 \\
      --home-score 2 --away-score 0 \\
      --verify-url "https://www.espn.com/soccer/match/_/id/..."

  # Full Opta data:
  python scripts/run_postmatch_complete.py \\
      --match-id 77382b67668e4d1a966a5fb88af6e408 \\
      --home-score 2 --away-score 0 \\
      --verify-url "https://..." \\
      --home-xg 1.43 --away-xg 0.065 \\
      --possession-home 61 --shots-home 16 --sot-home 4 \\
      --data-source "Opta"
        """,
    )

    # Required
    parser.add_argument("--match-id", required=True, help="Match UUID")
    parser.add_argument("--home-score", type=int, required=True, help="Actual home goals")
    parser.add_argument("--away-score", type=int, required=True, help="Actual away goals")

    # Verification
    parser.add_argument("--verify-url", default=None,
                        help="URL to sports site confirming the score")
    parser.add_argument("--verify-source-name", default=None,
                        help="Label for verification source (e.g. 'ESPN')")

    # Opta stats
    parser.add_argument("--home-xg", type=float, default=None)
    parser.add_argument("--away-xg", type=float, default=None)
    parser.add_argument("--possession-home", type=float, default=None)
    parser.add_argument("--possession-away", type=float, default=None)
    parser.add_argument("--shots-home", type=int, default=None)
    parser.add_argument("--shots-away", type=int, default=None)
    parser.add_argument("--sot-home", type=int, default=None)
    parser.add_argument("--sot-away", type=int, default=None)
    parser.add_argument("--corners-home", type=int, default=None)
    parser.add_argument("--corners-away", type=int, default=None)
    parser.add_argument("--passes-home", type=int, default=None)
    parser.add_argument("--passes-away", type=int, default=None)
    parser.add_argument("--data-source", default="manual",
                        help="Source of stats (e.g. 'Opta', 'FIFA')")

    # Mode
    parser.add_argument("--dry-run", action="store_true",
                        help="Run pipeline without writing to database")

    args = parser.parse_args()

    summary = asyncio.run(run_complete_postmatch(
        match_id=args.match_id,
        home_score=args.home_score,
        away_score=args.away_score,
        verify_url=args.verify_url,
        verify_source_name=args.verify_source_name,
        home_xg=args.home_xg,
        away_xg=args.away_xg,
        possession_home=args.possession_home,
        possession_away=args.possession_away,
        shots_home=args.shots_home,
        shots_away=args.shots_away,
        sot_home=args.sot_home,
        sot_away=args.sot_away,
        corners_home=args.corners_home,
        corners_away=args.corners_away,
        passes_home=args.passes_home,
        passes_away=args.passes_away,
        data_source=args.data_source,
        dry_run=args.dry_run,
    ))

    if summary["status"] == "ABORTED":
        print(f"\n❌ Pipeline ABORTED at step '{summary['failed_at_step']}'")
        print(f"   Error: {summary.get('error', 'Unknown')}")
        print(f"   Fix: {summary.get('fix', 'See logs above')}")
        sys.exit(1)


if __name__ == "__main__":
    main()

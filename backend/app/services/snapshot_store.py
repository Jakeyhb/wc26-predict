"""Save prediction results as standardized PredictionSnapshot records."""

from __future__ import annotations

from typing import Any

from app.database import AsyncSessionLocal
from app.models.prediction_snapshot import PredictionSnapshot


async def save_prediction_snapshot(
    result: dict[str, Any],
    run_type: str = "baseline_v0",
    report_path: str | None = None,
    report_markdown: str | None = None,
) -> PredictionSnapshot:
    """Persist a prediction result as a standardized snapshot."""
    m = result["meta"]
    p = result["prediction"]
    e = result["elo"]

    # Determine confidence level
    missing_count = len(result.get("missing_data", []))
    if missing_count <= 1:
        confidence = "medium"
    elif missing_count <= 3:
        confidence = "low"
    else:
        confidence = "low"

    snapshot = PredictionSnapshot(
        match_id=m.get("match_id", ""),
        run_type=run_type,
        model_version="2.0.0",
        home_team=m["home_team"],
        away_team=m["away_team"],
        competition=m["competition"],
        match_time=m.get("match_date", None),
        baseline_probs={
            "home": p["home_win_prob"],
            "draw": p["draw_prob"],
            "away": p["away_win_prob"],
        },
        component_probs=result.get("component_probs"),
        market_probs=result.get("market_divergence", {}).get("applied") and {
            "home": result["market_divergence"].get("market_home_prob"),
        } or None,
        adjusted_probs={
            "home": p["home_win_prob"],
            "draw": p["draw_prob"],
            "away": p["away_win_prob"],
        },
        expected_goals={
            "home": p["home_xg"],
            "away": p["away_xg"],
        },
        top_scores=p.get("top3_scores", []),
        elo_ratings={
            "home": e["home_elo"],
            "away": e["away_elo"],
            "gap": e["rating_gap"],
            "k_factor": e["k_factor"],
        },
        active_event_ids=[],
        missing_inputs=[
            item["item"] for item in result.get("missing_data", [])
        ],
        confidence=confidence,
        calibration_monitor=p.get("calibration_monitor"),
        pipeline_params={
            "dc_converged": result["pipeline"].get("dc_converged"),
            "dc_nll": result["pipeline"].get("dc_nll"),
            "enhancer_algorithm": result["pipeline"].get("enhancer_algorithm"),
            "enhancer_rows": result["pipeline"].get("enhancer_rows"),
            "enhancer_features": result["pipeline"].get("enhancer_features"),
            "elo_matches": result["pipeline"].get("elo_matches"),
            "training_rows": m.get("training_rows"),
        },
        report_path=report_path,
        report_markdown=report_markdown,
    )

    async with AsyncSessionLocal() as db:
        db.add(snapshot)
        await db.commit()
        await db.refresh(snapshot)

    return snapshot

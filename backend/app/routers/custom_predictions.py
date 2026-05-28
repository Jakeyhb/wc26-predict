"""Custom prediction API — user-driven match predictions.

  POST /api/predictions/custom       — submit async prediction
  GET  /api/predictions/status/{id}  — poll prediction status
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.enums import CompetitionType, MatchStatus
from app.models.match import Match
from app.models.team import Team
from app.schemas.custom_prediction import (
    CustomPredictionRequest,
    CustomPredictionResponse,
    PredictionStatusResponse,
)

router = APIRouter(tags=["custom-predictions"])

# ── In-memory prediction store ────────────────────────────
# Maps prediction_id → {status, match_id, result, error, started_at}
_predictions: dict[str, dict] = {}


@router.post("/custom", response_model=CustomPredictionResponse)
async def submit_custom_prediction(req: CustomPredictionRequest):
    """Submit a custom prediction. Runs asynchronously — poll status endpoint for results."""
    if req.home_team.strip().lower() == req.away_team.strip().lower():
        raise HTTPException(status_code=400, detail="Home and away teams must be different")

    prediction_id = uuid.uuid4().hex[:12]
    _predictions[prediction_id] = {
        "status": "queued",
        "match_id": None,
        "result": None,
        "error": None,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    # Start prediction in background
    asyncio.create_task(
        _run_prediction(prediction_id, req.home_team, req.away_team, req.competition, req.is_neutral_venue)
    )

    return CustomPredictionResponse(
        prediction_id=prediction_id,
        match_id="pending",
        status="queued",
    )


@router.get("/status/{prediction_id}", response_model=PredictionStatusResponse)
async def get_prediction_status(prediction_id: str):
    """Poll prediction status and get results when complete."""
    entry = _predictions.get(prediction_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Prediction not found")

    return PredictionStatusResponse(
        prediction_id=prediction_id,
        status=entry["status"],
        match_id=entry.get("match_id"),
        result=entry.get("result"),
        error=entry.get("error"),
    )


# ── Background prediction runner ───────────────────────────

async def _run_prediction(prediction_id: str, home_name: str, away_name: str, competition: str, neutral: bool):
    try:
        _predictions[prediction_id]["status"] = "running"

        from app.services.prediction_orchestrator import PredictionOrchestrator
        from app.models.team import Team
        from app.models.match import Match

        async with AsyncSessionLocal() as db:
            # Resolve or create teams
            home_team = await _resolve_or_create_team(db, home_name)
            away_team = await _resolve_or_create_team(db, away_name)

            # Find or create match record
            match_id = _hash_match_id(home_team.id, away_team.id, competition)
            match = await db.get(Match, match_id)
            if not match:
                match = Match(
                    id=match_id,
                    external_id=f"adhoc_{home_team.id[:8]}_{away_team.id[:8]}_{int(datetime.now(timezone.utc).timestamp())}",
                    home_team_id=home_team.id,
                    away_team_id=away_team.id,
                    match_date=datetime.now(timezone.utc),
                    competition=competition,
                    competition_type=CompetitionType.NATIONAL,
                    competition_weight=1.0,
                    is_neutral_venue=neutral,
                    status=MatchStatus.SCHEDULED,
                )
                db.add(match)
                await db.flush()

            _predictions[prediction_id]["match_id"] = str(match.id)
            await db.commit()

        # Run prediction in a fresh DB session
        async with AsyncSessionLocal() as db:
            orchestrator = PredictionOrchestrator()
            run_id = await orchestrator.run_prediction(
                match_id=match.id,
                run_type="t_minus_24h",
                db=db,
            )

        # Fetch result
        async with AsyncSessionLocal() as db:
            from app.models.prediction_run import PredictionRun
            result = await db.execute(
                select(PredictionRun).where(PredictionRun.id == run_id)
            )
            run = result.scalar_one_or_none()
            if run:
                _predictions[prediction_id]["result"] = {
                    "prediction_run_id": str(run.id),
                    "home_win_prob": run.home_win_prob,
                    "draw_prob": run.draw_prob,
                    "away_win_prob": run.away_win_prob,
                    "home_xg": run.home_xg,
                    "away_xg": run.away_xg,
                    "top3_scores": run.top3_scores,
                    "confidence_score": run.confidence_score,
                    "risk_tags": run.risk_tags,
                    "model_version": run.model_version,
                    "home_team": home_name,
                    "away_team": away_name,
                    "competition": competition,
                    "created_at": run.created_at.isoformat() if run.created_at else None,
                }

        _predictions[prediction_id]["status"] = "completed"

    except Exception as exc:
        _predictions[prediction_id]["status"] = "failed"
        _predictions[prediction_id]["error"] = str(exc)


async def _resolve_or_create_team(db: AsyncSession, name: str) -> Team:
    """Find an existing team by name or create a new one."""
    from app.services.team_resolver import TeamResolver

    resolver = TeamResolver()
    team = await resolver.resolve_team(db, name)
    if not team:
        import hashlib
        tid = hashlib.md5(f"nt_{name.lower().strip()}".encode()).hexdigest()
        team = Team(id=tid, name=name, team_type="national", elo_rating=1500.0)
        db.add(team)
        await db.flush()
    return team


def _hash_match_id(home_id: str, away_id: str, competition: str) -> str:
    import hashlib
    raw = f"custom_{home_id}_{away_id}_{competition}"
    return hashlib.md5(raw.encode()).hexdigest()

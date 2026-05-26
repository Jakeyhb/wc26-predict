from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy import func, select, text

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models import Match, NewsSignal, PredictionRun
from app.models.enums import ReviewStatus

router = APIRouter(tags=["health"])
settings = get_settings()

async def _health_payload() -> tuple[dict[str, object], int]:
    now = datetime.now(UTC)
    database_ok = False
    redis_ok = False
    matches_count = 0
    predictions_count = 0
    last_prediction_at = None
    pending_signals_count = 0

    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
            database_ok = True
            matches_count = int(await db.scalar(select(func.count()).select_from(Match)) or 0)
            predictions_count = int(await db.scalar(select(func.count()).select_from(PredictionRun)) or 0)
            last_prediction_at = await db.scalar(select(func.max(PredictionRun.created_at)))
            pending_signals_count = int(
                await db.scalar(
                    select(func.count()).select_from(NewsSignal).where(NewsSignal.review_status == ReviewStatus.PENDING)
                )
                or 0
            )
    except Exception as exc:
        payload = {
            "status": "down",
            "timestamp": now.isoformat(),
            "checks": {
                "database": "error",
                "redis": "unknown",
                "matches_count": 0,
                "predictions_count": 0,
                "last_prediction_at": None,
                "pending_signals_count": 0,
            },
            "detail": str(exc),
        }
        return payload, status.HTTP_503_SERVICE_UNAVAILABLE

    try:
        redis = Redis.from_url(settings.redis_url)
        redis_ok = bool(redis.ping())
    except Exception:
        redis_ok = False

    overall_status = "ok" if database_ok and redis_ok else "degraded"
    payload = {
        "status": overall_status,
        "timestamp": now.isoformat(),
        "checks": {
            "database": "ok",
            "redis": "ok" if redis_ok else "error",
            "matches_count": matches_count,
            "predictions_count": predictions_count,
            "last_prediction_at": last_prediction_at.isoformat() if last_prediction_at else None,
            "pending_signals_count": pending_signals_count,
        },
    }
    return payload, status.HTTP_200_OK


@router.get("/health")
@router.get("/api/health")
async def healthcheck() -> JSONResponse:
    payload, status_code = await _health_payload()
    return JSONResponse(status_code=status_code, content=payload)

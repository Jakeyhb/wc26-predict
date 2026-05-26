from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.news_signal import NewsSignal
from app.models.enums import ReviewStatus

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("/matches/{match_id}/approved")
async def get_approved_signals(match_id: UUID, db: AsyncSession = Depends(get_db)) -> list[dict[str, object]]:
    result = await db.execute(
        select(NewsSignal)
        .where(NewsSignal.match_id == match_id, NewsSignal.review_status == ReviewStatus.APPROVED)
        .order_by(NewsSignal.created_at.desc())
    )
    signals = result.scalars().all()
    return [
        {
            "id": signal.id,
            "signal_type": signal.signal_type,
            "impact_direction": signal.impact_direction,
            "summary_zh": signal.summary_zh,
            "confidence": signal.confidence,
            "source_reliability": signal.source_reliability,
            "key_players": signal.key_players,
        }
        for signal in signals
    ]


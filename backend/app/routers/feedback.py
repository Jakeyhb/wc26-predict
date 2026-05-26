from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Feedback
from app.rate_limit import limiter
from app.schemas.feedback import FeedbackCreateRequest, FeedbackResponse

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse)
@limiter.limit("20/minute")
async def create_feedback(
    request: Request,
    payload: FeedbackCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> FeedbackResponse:
    feedback = Feedback(
        match_id=payload.match_id,
        article_id=payload.article_id,
        feedback_type=payload.feedback_type,
        description=payload.description,
        contact=payload.contact,
        status="open",
    )
    db.add(feedback)
    await db.commit()
    return FeedbackResponse(status="received", message="感谢反馈，我们会认真处理")

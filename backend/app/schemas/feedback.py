from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class FeedbackCreateRequest(BaseModel):
    match_id: UUID | None = None
    article_id: UUID | None = None
    feedback_type: str
    description: str = Field(min_length=1, max_length=500)
    contact: str | None = Field(default=None, max_length=200)


class FeedbackResponse(BaseModel):
    status: str
    message: str


class FeedbackItem(BaseModel):
    id: UUID
    match_id: UUID | None = None
    article_id: UUID | None = None
    feedback_type: str
    description: str
    contact: str | None = None
    status: str
    created_at: datetime

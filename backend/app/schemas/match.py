from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.prediction import MatchCard


class ReviewSignalSummary(BaseModel):
    signal_id: UUID
    summary_zh: str
    signal_type: str
    verdict: str
    notes: str | None = None


class ReviewRunSummary(BaseModel):
    prediction_run_id: UUID
    run_type: str
    created_at: datetime
    predicted_top_score: str
    actual_score: str
    brier_score: float
    log_loss: float
    exact_score_hit: bool
    top3_hit: bool


class ReviewSummary(BaseModel):
    match_id: UUID
    actual_score: str
    actual_result: str
    runs: list[ReviewRunSummary]
    signal_reviews: list[ReviewSignalSummary]


class EvidenceItem(BaseModel):
    id: UUID
    article_title: str
    source_name: str | None = None
    source_url: str
    evidence_snippet: str
    published_at: datetime | None = None
    relevance_score: float
    signal_summary: str | None = None
    used_in_article: bool


class EvidenceResponse(BaseModel):
    match_id: UUID
    evidence_items: list[EvidenceItem]
    total_articles_analyzed: int
    evidence_count: int


class ScheduleGroup(BaseModel):
    date: str
    date_label: str
    matches: list[MatchCard]


class ScheduleResponse(BaseModel):
    groups: list[ScheduleGroup]
    total: int
    total_pages: int
    current_page: int

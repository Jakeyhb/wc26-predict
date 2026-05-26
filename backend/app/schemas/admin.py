from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PendingSignalItem(BaseModel):
    id: UUID
    article_id: UUID
    match_id: UUID | None = None
    team_id: UUID | None = None
    signal_type: str
    impact_direction: str
    confidence: float
    summary_zh: str
    source_reliability: float
    key_players: list[str]
    player_name: str | None = None
    claim: str | None = None
    evidence_snippet: str | None = None
    normalized_availability: str | None = None
    expected_minutes_delta: float | None = None
    effective_until: datetime | None = None
    contradiction_risk: str | None = None
    conflict_group_id: str | None = None
    created_at: datetime
    article_title: str
    source_name: str | None = None


class SignalReviewRequest(BaseModel):
    status: str
    enters_model: bool = False
    notes: str | None = None
    signal_ids: list[UUID] = Field(default_factory=list)
    reviewed_by: str = "admin"


class ManualSignalCreateRequest(BaseModel):
    article_title: str
    article_content: str = ""
    source_name: str = "manual"
    source_url: str = "manual://entry"
    language: str = "zh"
    team_name: str | None = None
    match_id: UUID | None = None
    signal_type: str
    impact_direction: str
    confidence: float
    summary_zh: str
    key_players: list[str] = Field(default_factory=list)
    source_reliability: float = 0.95
    review_notes: str | None = None
    enters_model: bool = True
    reviewed_by: str = "admin"


class PendingArticleItem(BaseModel):
    id: UUID
    match_id: UUID
    prediction_run_id: UUID
    title: str
    body: str
    article_version: int
    created_at: datetime


class PublishArticleRequest(BaseModel):
    notes: str | None = None
    published_by: str = "admin"


class RecentAccuracyItem(BaseModel):
    prediction_run_id: UUID
    match_id: UUID
    brier_score: float
    log_loss: float
    top3_hit: bool


class CompetitionBreakdownItem(BaseModel):
    match_count: int
    prediction_count: int


class CalibratorStatus(BaseModel):
    is_fitted: bool
    training_samples: int
    fitted_at: datetime | None = None
    expected_calibration_error: float | None = None


class RecentPredictionVolumeItem(BaseModel):
    competition: str
    competition_zh: str
    prediction_count: int


class HermesDigestItem(BaseModel):
    label: str
    detail: str
    tone: str


class HermesTaskSnapshot(BaseModel):
    name: str
    last_run: datetime | None = None
    age_minutes: int | None = None
    stale: bool


class HermesDigestResponse(BaseModel):
    generated_at: datetime
    attention_level: str
    summary: str
    counts: dict[str, int]
    focus_items: list[HermesDigestItem]
    watch_items: list[HermesDigestItem]
    stale_tasks: list[HermesTaskSnapshot]
    calibrator_status: CalibratorStatus


class AdminDashboardSummary(BaseModel):
    new_articles_today: int
    pending_signals: int
    prediction_runs_today: int
    recent_accuracy: list[RecentAccuracyItem]
    recent_5_matches_avg_brier_score: float | None = None
    last_7_days_avg_brier_score: float | None = None
    total_predictions_made: int
    top3_hit_rate_overall: float | None = None
    competition_breakdown: dict[str, CompetitionBreakdownItem]
    calibrator_status: CalibratorStatus
    beat_tasks_last_run: dict[str, datetime | None]
    recent_prediction_counts_7d: list[RecentPredictionVolumeItem]


class TriggerPredictionRequest(BaseModel):
    run_type: str


class TriggerPredictionResponse(BaseModel):
    prediction_run_id: UUID
    status: str = "ok"


class FeedbackStatusUpdateRequest(BaseModel):
    status: str = "resolved"


class ConflictSignalGroupItem(BaseModel):
    conflict_group_id: str
    signals: list[PendingSignalItem]


class ManualMatchCreateRequest(BaseModel):
    home_team_name: str
    away_team_name: str
    match_date: datetime
    competition: str
    stage: str | None = None
    venue: str | None = None
    is_neutral_venue: bool = True
    competition_weight: float = 1.0


class ManualMatchCreateResponse(BaseModel):
    match_id: UUID
    status: str = "created"


class MatchResultUpdateRequest(BaseModel):
    home_goals: int
    away_goals: int

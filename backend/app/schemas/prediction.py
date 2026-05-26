from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import PredictionRunType
from app.schemas.common import TeamRef


class ScoreProbability(BaseModel):
    score: str
    prob: float


class ApprovedSignalItem(BaseModel):
    id: UUID
    signal_type: str
    impact_direction: str
    summary_zh: str
    source_reliability: float
    confidence: float
    key_players: list[str]
    player_name: str | None = None
    claim: str | None = None
    evidence_snippet: str | None = None
    normalized_availability: str | None = None
    expected_minutes_delta: float | None = None
    effective_until: datetime | None = None
    contradiction_risk: str | None = None
    conflict_group_id: str | None = None
    reviewed_at: datetime | None = None


class PredictionSnapshot(BaseModel):
    id: UUID
    match_id: UUID
    run_type: PredictionRunType
    model_version: str
    as_of_time: datetime
    created_at: datetime
    home_win_prob: float
    draw_prob: float
    away_win_prob: float
    home_xg: float
    away_xg: float
    score_matrix: list[list[float]]
    top3_scores: list[ScoreProbability]
    confidence_score: float
    risk_tags: list[str]
    approved_signals: list[ApprovedSignalItem]
    input_feature_snapshot: dict[str, object]
    article_title: str | None = None
    article_body: str | None = None
    article_status: str


class PredictionHistoryItem(BaseModel):
    id: UUID
    run_type: PredictionRunType
    as_of_time: datetime
    created_at: datetime
    home_win_prob: float
    draw_prob: float
    away_win_prob: float
    home_xg: float
    away_xg: float
    confidence_score: float
    risk_tags: list[str]


class MatchCardPrediction(BaseModel):
    latest_run_id: UUID | None = None
    home_win_prob: float | None = None
    draw_prob: float | None = None
    away_win_prob: float | None = None
    confidence_score: float | None = None
    run_type: PredictionRunType | None = None


class MatchCard(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    match_date: datetime
    competition: str
    competition_type: str
    competition_code: str | None = None
    competition_name_zh: str | None = None
    stage: str | None = None
    venue: str | None = None
    status: str
    home_team: TeamRef
    away_team: TeamRef
    latest_prediction: MatchCardPrediction | None = None

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AccuracyOverall(BaseModel):
    total_predictions: int
    brier_score_avg: float | None = None
    top3_hit_rate: float | None = None
    log_loss_avg: float | None = None
    last_updated: datetime | None = None


class AccuracyByCompetitionItem(BaseModel):
    competition: str
    competition_zh: str
    total: int
    brier_score: float | None = None
    top3_hit_rate: float | None = None


class RecentThirtySummary(BaseModel):
    brier_score: float | None = None
    top3_hit_rate: float | None = None
    trend: str


class AccuracyStatsResponse(BaseModel):
    overall: AccuracyOverall
    by_competition: list[AccuracyByCompetitionItem]
    recent_30: RecentThirtySummary
    calibration_applied: bool
    model_version: str


class RecentPredictionItem(BaseModel):
    match_id: UUID
    match_date: datetime
    home_team_zh: str
    away_team_zh: str
    competition: str
    competition_zh: str
    predicted_home_win: float
    predicted_draw: float
    predicted_away_win: float
    top1_score: str
    actual_home_goals: int
    actual_away_goals: int
    result: str
    prediction_correct: bool
    top3_hit: bool
    brier_score: float


class RecentPredictionsResponse(BaseModel):
    items: list[RecentPredictionItem]

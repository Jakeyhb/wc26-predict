"""Pydantic models for custom prediction API."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TeamItem(BaseModel):
    id: str
    name: str
    name_zh: str | None = None
    fifa_code: str | None = None
    team_type: str  # national | club


class CustomPredictionRequest(BaseModel):
    home_team: str = Field(..., min_length=1, description="Home team name")
    away_team: str = Field(..., min_length=1, description="Away team name")
    competition: str = Field(default="Custom Match")
    is_neutral_venue: bool = False


class CustomPredictionResponse(BaseModel):
    prediction_id: str
    match_id: str
    status: str = "queued"


class PredictionStatusResponse(BaseModel):
    prediction_id: str
    status: str  # queued | running | completed | failed
    match_id: str | None = None
    result: dict | None = None
    error: str | None = None

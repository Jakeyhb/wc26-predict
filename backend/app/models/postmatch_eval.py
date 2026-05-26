from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import MatchResultCode


class PostmatchEval(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "postmatch_eval"

    prediction_run_id: Mapped[UUID] = mapped_column(ForeignKey("prediction_runs.id", ondelete="CASCADE"), nullable=False)
    actual_home_goals: Mapped[int] = mapped_column(nullable=False)
    actual_away_goals: Mapped[int] = mapped_column(nullable=False)
    actual_result: Mapped[MatchResultCode] = mapped_column(String(5), nullable=False)
    brier_score: Mapped[float] = mapped_column(Float, nullable=False)
    log_loss: Mapped[float] = mapped_column(Float, nullable=False)
    exact_score_hit: Mapped[bool] = mapped_column(Boolean, nullable=False)
    top3_hit: Mapped[bool] = mapped_column(Boolean, nullable=False)
    calibration_bucket: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    prediction_run = relationship("PredictionRun", back_populates="postmatch_evaluations")

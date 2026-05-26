from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import SignalEvalLabel


class PostmatchSignalEval(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "postmatch_signal_eval"

    match_id: Mapped[UUID] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    prediction_run_id: Mapped[UUID] = mapped_column(ForeignKey("prediction_runs.id", ondelete="CASCADE"), nullable=False)
    signal_id: Mapped[UUID] = mapped_column(ForeignKey("news_signals.id", ondelete="CASCADE"), nullable=False)
    verdict: Mapped[SignalEvalLabel] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    match = relationship("Match", back_populates="signal_evaluations")
    prediction_run = relationship("PredictionRun", back_populates="signal_evaluations")
    signal = relationship("NewsSignal", back_populates="evaluations")

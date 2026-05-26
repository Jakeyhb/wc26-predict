from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONVariant, UUIDPrimaryKeyMixin
from app.models.enums import PredictionRunType


class PredictionRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "prediction_runs"
    __table_args__ = (
        Index("ix_prediction_runs_match_created", "match_id", "created_at"),
    )

    match_id: Mapped[UUID] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    run_type: Mapped[PredictionRunType] = mapped_column(String(20), nullable=False)
    model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    as_of_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    home_win_prob: Mapped[float] = mapped_column(Float, nullable=False)
    draw_prob: Mapped[float] = mapped_column(Float, nullable=False)
    away_win_prob: Mapped[float] = mapped_column(Float, nullable=False)
    home_xg: Mapped[float] = mapped_column(Float, nullable=False)
    away_xg: Mapped[float] = mapped_column(Float, nullable=False)
    score_matrix: Mapped[list[list[float]]] = mapped_column(JSONVariant, nullable=False)
    top3_scores: Mapped[list[dict[str, float | str]]] = mapped_column(JSONVariant, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_tags: Mapped[list[str]] = mapped_column(JSONVariant, default=list, nullable=False)
    input_feature_snapshot: Mapped[dict[str, object]] = mapped_column(JSONVariant, default=dict, nullable=False)
    approved_signals: Mapped[list[dict[str, object]]] = mapped_column(JSONVariant, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    match = relationship("Match", back_populates="prediction_runs")
    postmatch_evaluations = relationship("PostmatchEval", back_populates="prediction_run")
    content_articles = relationship("ContentArticle", back_populates="prediction_run")
    signal_evaluations = relationship("PostmatchSignalEval", back_populates="prediction_run")
    evidence_items = relationship("ArticleEvidence", back_populates="prediction_run")

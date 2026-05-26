from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import CompetitionType
from app.models.enums import MatchStatus


class Match(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "matches"
    __table_args__ = (
        Index("ix_matches_match_date_status", "match_date", "status"),
    )

    external_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    home_team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    away_team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    match_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    competition: Mapped[str] = mapped_column(String(50), nullable=False)
    competition_type: Mapped[CompetitionType] = mapped_column(
        String(20),
        default=CompetitionType.NATIONAL,
        server_default=CompetitionType.NATIONAL.value,
        nullable=False,
    )
    competition_weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    stage: Mapped[str | None] = mapped_column(String(50))
    venue: Mapped[str | None] = mapped_column(String(100))
    is_neutral_venue: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[MatchStatus] = mapped_column(String(20), default=MatchStatus.SCHEDULED, nullable=False)

    home_team = relationship("Team", back_populates="home_matches", foreign_keys=[home_team_id])
    away_team = relationship("Team", back_populates="away_matches", foreign_keys=[away_team_id])
    result = relationship("MatchResult", back_populates="match", uselist=False, cascade="all, delete-orphan")
    news_signals = relationship("NewsSignal", back_populates="match")
    prediction_runs = relationship("PredictionRun", back_populates="match")
    content_articles = relationship("ContentArticle", back_populates="match")
    signal_evaluations = relationship("PostmatchSignalEval", back_populates="match")
    evidence_items = relationship("ArticleEvidence", back_populates="match")
    feedback_items = relationship("Feedback", back_populates="match")


class MatchResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "match_results"

    match_id: Mapped[UUID] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), unique=True, nullable=False)
    home_goals: Mapped[int] = mapped_column(nullable=False)
    away_goals: Mapped[int] = mapped_column(nullable=False)
    home_xg: Mapped[float | None]
    away_xg: Mapped[float | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    match = relationship("Match", back_populates="result")

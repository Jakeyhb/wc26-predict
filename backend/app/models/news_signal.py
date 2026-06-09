from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONVariant, UUIDPrimaryKeyMixin
from app.models.enums import ImpactDirection, ReviewStatus, SignalType


class NewsSignal(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "news_signals"
    __table_args__ = (
        Index("ix_news_signals_review_status_created_at", "review_status", "created_at"),
    )

    article_id: Mapped[UUID] = mapped_column(ForeignKey("news_articles.id", ondelete="CASCADE"), nullable=False)
    match_id: Mapped[UUID | None] = mapped_column(ForeignKey("matches.id"))
    team_id: Mapped[UUID | None] = mapped_column(ForeignKey("teams.id"))
    signal_type: Mapped[SignalType] = mapped_column(String(30), nullable=False)
    impact_direction: Mapped[ImpactDirection] = mapped_column(String(10), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    key_players: Mapped[list[str]] = mapped_column(JSONVariant, default=list, nullable=False)
    summary_zh: Mapped[str] = mapped_column(String(200), nullable=False)
    player_name: Mapped[str | None] = mapped_column(String(100))
    claim: Mapped[str | None] = mapped_column(String(300))
    evidence_snippet: Mapped[str | None] = mapped_column(String(300))
    normalized_availability: Mapped[str | None] = mapped_column(String(30))
    expected_minutes_delta: Mapped[float | None] = mapped_column(Float)
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    conflict_group_id: Mapped[str | None] = mapped_column(String(50))
    contradiction_risk: Mapped[str | None] = mapped_column(String(10))
    source_reliability: Mapped[float] = mapped_column(Float, nullable=False)
    review_status: Mapped[ReviewStatus] = mapped_column(String(20), default=ReviewStatus.PENDING, nullable=False)
    review_notes: Mapped[str | None] = mapped_column(String(500))
    reviewed_by: Mapped[str | None] = mapped_column(String(50))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_id: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True, default=None)
    enters_model: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    article = relationship("NewsArticle", back_populates="signals")
    match = relationship("Match", back_populates="news_signals")
    team = relationship("Team", back_populates="news_signals")
    evaluations = relationship("PostmatchSignalEval", back_populates="signal")
    evidence_items = relationship("ArticleEvidence", back_populates="signal")

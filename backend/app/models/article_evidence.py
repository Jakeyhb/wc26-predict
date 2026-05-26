from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin


class ArticleEvidence(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "article_evidence"
    __table_args__ = (
        Index("ix_article_evidence_match_created", "match_id", "created_at"),
    )

    match_id: Mapped[UUID] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    prediction_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("prediction_runs.id", ondelete="CASCADE"))
    article_id: Mapped[UUID] = mapped_column(ForeignKey("news_articles.id", ondelete="CASCADE"), nullable=False)
    signal_id: Mapped[UUID | None] = mapped_column(ForeignKey("news_signals.id", ondelete="SET NULL"))
    evidence_snippet: Mapped[str] = mapped_column(Text, nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    used_in_article: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    match = relationship("Match", back_populates="evidence_items")
    prediction_run = relationship("PredictionRun", back_populates="evidence_items")
    article = relationship("NewsArticle", back_populates="evidence_items")
    signal = relationship("NewsSignal", back_populates="evidence_items")

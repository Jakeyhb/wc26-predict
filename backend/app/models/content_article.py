from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONVariant, TimestampMixin, UUIDPrimaryKeyMixin


class ContentArticle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "content_articles"

    match_id: Mapped[UUID] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    prediction_run_id: Mapped[UUID] = mapped_column(ForeignKey("prediction_runs.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    article_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    correction_log: Mapped[list[dict[str, object]]] = mapped_column(JSONVariant, default=list, nullable=False)

    match = relationship("Match", back_populates="content_articles")
    prediction_run = relationship("PredictionRun", back_populates="content_articles")
    feedback_items = relationship("Feedback", back_populates="article")

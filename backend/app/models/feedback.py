from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Feedback(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feedback"

    match_id: Mapped[UUID | None] = mapped_column(ForeignKey("matches.id", ondelete="SET NULL"))
    article_id: Mapped[UUID | None] = mapped_column(ForeignKey("content_articles.id", ondelete="SET NULL"))
    feedback_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    contact: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)

    match = relationship("Match", back_populates="feedback_items")
    article = relationship("ContentArticle", back_populates="feedback_items")

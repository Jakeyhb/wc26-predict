from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin, embedding_type


class NewsArticle(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "news_articles"

    external_id: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(100))
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(10))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(embedding_type(), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    signals = relationship("NewsSignal", back_populates="article", cascade="all, delete-orphan")
    evidence_items = relationship("ArticleEvidence", back_populates="article", cascade="all, delete-orphan")

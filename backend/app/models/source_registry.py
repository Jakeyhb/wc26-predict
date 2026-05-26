from __future__ import annotations

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SourceRegistry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "source_registry"

    domain: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    reliability_score: Mapped[float] = mapped_column(Float, nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


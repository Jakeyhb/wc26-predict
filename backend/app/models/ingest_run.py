from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONVariant, UUIDPrimaryKeyMixin


class IngestRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ingest_runs"

    pipeline: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_inserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSONVariant, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)


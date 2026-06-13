"""Closed-loop resolution ledger.

Records whether legacy rows can be safely attached to a match/prediction run.
This keeps audit output honest: unresolved old data should be quarantined, not
silently treated as clean learning data.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Float, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONVariant, TimestampMixin


class ClosedLoopResolution(Base, TimestampMixin):
    __tablename__ = "closed_loop_resolution_ledger"
    __table_args__ = (
        UniqueConstraint("entity_table", "entity_id", name="uq_closed_loop_resolution_entity"),
        Index("ix_closed_loop_resolution_status", "status"),
        Index("ix_closed_loop_resolution_match", "resolved_match_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_table: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    resolved_match_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resolved_prediction_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    resolver_version: Mapped[str] = mapped_column(String(32), nullable=False, default="closed_loop_v1")
    source_payload: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)

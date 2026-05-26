"""Lineup probe log model — records lineup availability timing from football-data.org."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class LineupProbeLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Records a single lineup availability probe for a match.

    Used to empirically determine when football-data.org starts returning
    lineup/bench/formation data before kickoff.
    """

    __tablename__ = "lineup_probe_logs"

    match_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("matches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    external_match_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Probe timing
    probe_time: Mapped[str] = mapped_column(String(30), nullable=False)  # ISO 8601
    minutes_to_kickoff: Mapped[int] = mapped_column(Integer, nullable=False)

    # What we found
    has_lineup: Mapped[bool] = mapped_column(default=False, nullable=False)
    has_bench: Mapped[bool] = mapped_column(default=False, nullable=False)
    has_formation: Mapped[bool] = mapped_column(default=False, nullable=False)
    has_coach: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Match status from API (SCHEDULED, TIMED, IN_PLAY, FINISHED, etc.)
    api_match_status: Mapped[str | None] = mapped_column(String(20))

    # API lastUpdated timestamp
    api_last_updated: Mapped[str | None] = mapped_column(String(30))

    # Raw response path (optional, for later inspection)
    raw_response_path: Mapped[str | None] = mapped_column(String(200))

    # Notes
    notes: Mapped[str | None] = mapped_column(Text)

"""Post-match team statistics with source provenance."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONVariant, TimestampMixin, UUIDPrimaryKeyMixin


class PostmatchTeamStats(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Traceable team-level statistics for a completed match.

    `match_results` remains the compact score/xG compatibility table. This table
    carries wider post-match stats plus source timing so future backtests can
    prove when a data point became available.
    """

    __tablename__ = "postmatch_team_stats"
    __table_args__ = (
        UniqueConstraint("match_id", "provider", "source_match_id", name="uq_postmatch_stats_source_match"),
        Index("ix_postmatch_stats_match", "match_id"),
        Index("ix_postmatch_stats_provider", "provider"),
    )

    match_id: Mapped[UUID] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    source_match_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_time: Mapped[str] = mapped_column(String(40), nullable=False)
    available_at: Mapped[str] = mapped_column(String(40), nullable=False)
    captured_at: Mapped[str] = mapped_column(String(40), nullable=False)

    home_xg: Mapped[float | None] = mapped_column(Float)
    away_xg: Mapped[float | None] = mapped_column(Float)
    home_shots: Mapped[int | None] = mapped_column(Integer)
    away_shots: Mapped[int | None] = mapped_column(Integer)
    home_shots_on_target: Mapped[int | None] = mapped_column(Integer)
    away_shots_on_target: Mapped[int | None] = mapped_column(Integer)
    home_yellow_cards: Mapped[int | None] = mapped_column(Integer)
    away_yellow_cards: Mapped[int | None] = mapped_column(Integer)
    home_red_cards: Mapped[int | None] = mapped_column(Integer)
    away_red_cards: Mapped[int | None] = mapped_column(Integer)
    home_corners: Mapped[int | None] = mapped_column(Integer)
    away_corners: Mapped[int | None] = mapped_column(Integer)
    home_possession: Mapped[float | None] = mapped_column(Float)
    away_possession: Mapped[float | None] = mapped_column(Float)

    raw_payload: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text)

    match = relationship("Match")

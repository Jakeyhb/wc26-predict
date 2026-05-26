"""Standings model — league/competition standings data."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Standing(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single row in a competition standings table."""

    __tablename__ = "standings"
    __table_args__ = (
        UniqueConstraint("competition_code", "season", "team_name", name="uq_standings_comp_season_team"),
    )

    competition_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    season: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    team_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Position data
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    played_games: Mapped[int] = mapped_column(Integer, default=0)
    won: Mapped[int] = mapped_column(Integer, default=0)
    drawn: Mapped[int] = mapped_column(Integer, default=0)
    lost: Mapped[int] = mapped_column(Integer, default=0)
    goals_for: Mapped[int] = mapped_column(Integer, default=0)
    goals_against: Mapped[int] = mapped_column(Integer, default=0)
    goal_difference: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[int] = mapped_column(Integer, default=0)

    # Optional metadata
    form: Mapped[str | None] = mapped_column(String(20))  # e.g. "W,W,D,L,W"
    group_name: Mapped[str | None] = mapped_column(String(50))  # for group-stage comps

    # Source tracking
    source: Mapped[str] = mapped_column(String(50), default="football-data.org")
    fetched_at: Mapped[str | None] = mapped_column(String(30))

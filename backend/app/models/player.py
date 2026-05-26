from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Player(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "players"

    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    name_zh: Mapped[str | None] = mapped_column(String(100))
    position: Mapped[str | None] = mapped_column(String(20))
    is_key_player: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_club: Mapped[str | None] = mapped_column(String(100))

    # Phase A additions (P2-3)
    importance_level: Mapped[str] = mapped_column(
        String(20), default="unknown", nullable=False
    )  # key | starter | rotation | backup | unknown
    status: Mapped[str] = mapped_column(
        String(20), default="unknown", nullable=False
    )  # fit | doubtful | injured | suspended | unknown
    source: Mapped[str | None] = mapped_column(String(200))
    # source_url for this player's data

    team = relationship("Team", back_populates="players")


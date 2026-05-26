from __future__ import annotations

from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import TeamType


class Team(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teams"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    name_zh: Mapped[str | None] = mapped_column(String(100))
    fifa_code: Mapped[str | None] = mapped_column(String(3), unique=True)
    team_type: Mapped[TeamType] = mapped_column(
        String(20),
        default=TeamType.NATIONAL,
        server_default=TeamType.NATIONAL.value,
        nullable=False,
    )
    country: Mapped[str | None] = mapped_column(String(100))
    confederation: Mapped[str | None] = mapped_column(String(10))
    elo_rating: Mapped[float] = mapped_column(Float, default=1500.0, nullable=False)

    players = relationship("Player", back_populates="team", cascade="all, delete-orphan")
    aliases = relationship("TeamAlias", back_populates="team", cascade="all, delete-orphan")
    home_matches = relationship(
        "Match",
        back_populates="home_team",
        foreign_keys="Match.home_team_id",
    )
    away_matches = relationship(
        "Match",
        back_populates="away_team",
        foreign_keys="Match.away_team_id",
    )
    news_signals = relationship("NewsSignal", back_populates="team")

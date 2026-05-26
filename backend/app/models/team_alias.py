from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TeamAlias(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "team_aliases"
    __table_args__ = (
        Index("ix_team_aliases_alias_normalized", "alias_normalized", unique=True),
    )

    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    alias: Mapped[str] = mapped_column(String(100), nullable=False)
    alias_normalized: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="manual", nullable=False)

    team = relationship("Team", back_populates="aliases")


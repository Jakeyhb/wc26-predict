"""MarketOdds model — stores implied probabilities from betting markets.

Design principles:
1. Only store implied probabilities (after vig removal), NOT raw odds numbers
2. vig_removed=True ensures we never expose raw betting odds
3. sample_bookmakers tracks how many sources were aggregated
"""

from __future__ import annotations

from sqlalchemy import DateTime, Float, Integer, Boolean, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MarketOdds(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Market-implied probabilities for a match, vig-removed."""

    __tablename__ = "market_odds"

    match_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    fetched_at: Mapped[str] = mapped_column(String(30), nullable=False)

    # Implied probabilities (after vig removal, sum ~= 1.0)
    home_implied_prob: Mapped[float] = mapped_column(Float, nullable=False)
    draw_implied_prob: Mapped[float] = mapped_column(Float, nullable=False)
    away_implied_prob: Mapped[float] = mapped_column(Float, nullable=False)

    # Metadata
    vig_removed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    vig_amount: Mapped[float | None] = mapped_column(Float)  # original vig
    sample_bookmakers: Mapped[int] = mapped_column(Integer, default=1)
    provider: Mapped[str] = mapped_column(String(50), default="the-odds-api")

"""ContextPerformanceMatrix — tracks model accuracy per situational context.

Examples: derby matches, must-win games, neutral venues, etc.
Learns systematic biases so they can be corrected.
"""

from __future__ import annotations

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ContextPerformanceMatrix(Base):
    """Per-context performance tracker."""

    __tablename__ = "context_performance_matrix"

    context_tag: Mapped[str] = mapped_column(String(50), primary_key=True)

    total_matches: Mapped[int] = mapped_column(Integer, default=0)
    avg_brier_score: Mapped[float | None] = mapped_column(Float)
    avg_error_direction: Mapped[float | None] = mapped_column(
        Float, doc="Positive = overestimated home, negative = underestimated"
    )
    recommended_adjustment: Mapped[float] = mapped_column(Float, default=0.0)
    last_calibrated: Mapped[str | None] = mapped_column(String(30))

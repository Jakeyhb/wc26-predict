"""SignalTrackRecord — tracks per-signal-type accuracy for dynamic weighting.

Each signal type (INJURY, ROTATION_HINT, etc.) gets one row that
accumulates counts and computes accuracy. Every 100 updates,
current_weight_multiplier is recalculated.
"""

from __future__ import annotations

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SignalTrackRecord(Base):
    """Per-signal-type accuracy tracker for dynamic weight adjustment."""

    __tablename__ = "signal_track_record"

    signal_type: Mapped[str] = mapped_column(String(50), primary_key=True)

    total_used: Mapped[int] = mapped_column(Integer, default=0)
    accurate_count: Mapped[int] = mapped_column(Integer, default=0)
    misleading_count: Mapped[int] = mapped_column(Integer, default=0)
    neutral_count: Mapped[int] = mapped_column(Integer, default=0)

    # Computed in Python (SQLite doesn't support GENERATED ALWAYS AS)
    accuracy_rate: Mapped[float] = mapped_column(Float, default=0.5)
    current_weight_multiplier: Mapped[float] = mapped_column(Float, default=1.0)

    last_updated: Mapped[str | None] = mapped_column(String(30))

    # Initial data for 6 core signal types
    @classmethod
    def default_signals(cls) -> list[dict]:
        return [
            {"signal_type": "INJURY", "accuracy_rate": 0.5, "current_weight_multiplier": 1.0},
            {"signal_type": "SUSPENSION", "accuracy_rate": 0.5, "current_weight_multiplier": 1.0},
            {"signal_type": "ROTATION_HINT", "accuracy_rate": 0.5, "current_weight_multiplier": 1.0},
            {"signal_type": "MOTIVATION", "accuracy_rate": 0.5, "current_weight_multiplier": 1.0},
            {"signal_type": "WEATHER", "accuracy_rate": 0.5, "current_weight_multiplier": 1.0},
            {"signal_type": "LINEUP_RUMOR", "accuracy_rate": 0.5, "current_weight_multiplier": 1.0},
        ]

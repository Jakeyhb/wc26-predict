"""ModelWeightConfig — dynamic weight configuration table.

Replaces hardcoded constants with database-driven weights.
Updated by seasonal_weight_optimizer, read by all prediction layers.
"""

from __future__ import annotations

from sqlalchemy import String, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ModelWeightConfig(Base):
    """Key-value config for model weights and hyperparameters."""

    __tablename__ = "model_weight_config"

    config_key: Mapped[str] = mapped_column(String(50), primary_key=True)
    config_value: Mapped[float] = mapped_column(Float, nullable=False)
    previous_value: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[str | None] = mapped_column(String(30))
    update_reason: Mapped[str | None] = mapped_column(String(200))
    updated_by: Mapped[str] = mapped_column(String(50), default="manual")

"""Pre-match snapshot model — immutable, timestamped, traceable.

Captures the complete state of a prediction at generation time:
what data was available, what the models output, and what was missing.

This is the foundation for:
  - Reproducible predictions ("what did the model see at T-24h?")
  - Post-match audit ("did missing lineup data cause the error?")
  - Backtesting ("replay a prediction with historical data")
  - Weight change justification ("show before/after comparison")

Design: One row per prediction generation event. A single match can have
multiple snapshots (T-72h, T-24h, T-6h, T-1h, T-60min).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Float, JSON, DateTime, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PreMatchSnapshot(Base):
    __tablename__ = "pre_match_snapshots"

    # ── Identity ──
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    match_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)

    # ── Timing ──
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    kickoff_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    hours_to_kickoff: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Teams ──
    home_team: Mapped[str] = mapped_column(String(200), nullable=False)
    away_team: Mapped[str] = mapped_column(String(200), nullable=False)
    competition: Mapped[str] = mapped_column(String(200), nullable=False)
    is_neutral: Mapped[bool] = mapped_column(default=False)

    # ── Input data availability flags ──
    weather_available: Mapped[bool] = mapped_column(default=False)
    odds_available: Mapped[bool] = mapped_column(default=False)
    lineup_available: Mapped[bool] = mapped_column(default=False)
    injury_data_available: Mapped[bool] = mapped_column(default=False)
    news_signals_available: Mapped[bool] = mapped_column(default=False)

    # ── Input data snapshots (JSON blobs) ──
    weather_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    odds_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    lineup_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    injury_records: Mapped[list | None] = mapped_column(JSON, nullable=True)
    news_signal_ids: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

    # ── Model outputs (before fusion) ──
    component_probs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Keys: "dixon_coles", "enhancer", "elo", "pi_rating", "weibull", "market"
    # Each value: {"home": float, "draw": float, "away": float}

    # ── Final prediction ──
    final_home_prob: Mapped[float] = mapped_column(Float, nullable=False)
    final_draw_prob: Mapped[float] = mapped_column(Float, nullable=False)
    final_away_prob: Mapped[float] = mapped_column(Float, nullable=False)
    home_xg: Mapped[float | None] = mapped_column(Float, nullable=True)
    away_xg: Mapped[float | None] = mapped_column(Float, nullable=True)
    top_scores: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # ── Fusion metadata ──
    weight_config_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    weight_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    effective_weights: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fusion_graph: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model_disagreement: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Market data ──
    market_blended: Mapped[bool] = mapped_column(default=False)
    market_weight_used: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_divergence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Confidence & risk ──
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence_penalty: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_tags: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    pipeline_status: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # ── What was missing ──
    missing_inputs: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    degraded_reasons: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

    # ── Version tracking ──
    code_version: Mapped[str] = mapped_column(String(32), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    git_commit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_timestamps: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Source reference IDs — link to source data rows for full traceability
    odds_snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    weather_snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    injury_snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # ── Mode ──
    prediction_mode: Mapped[str] = mapped_column(String(32), default="full")

    # ── Optional: full report ──
    report_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<PreMatchSnapshot {self.id[:8]} "
            f"{self.home_team} vs {self.away_team} "
            f"[{self.prediction_mode}] T-{self.hours_to_kickoff or '?'}h>"
        )

    @property
    def freeze_time(self) -> datetime | None:
        """Explicit alias for snapshot_at — the moment this prediction was frozen."""
        return self.snapshot_at

    @property
    def total_input_availability(self) -> float:
        """Fraction of input categories that were available (0.0-1.0)."""
        inputs = [
            self.weather_available,
            self.odds_available,
            self.lineup_available,
            self.injury_data_available,
            self.news_signals_available,
        ]
        return sum(inputs) / len(inputs)

    @property
    def input_total(self) -> int:
        """Count of available input categories (0-5)."""
        return sum([
            self.weather_available,
            self.odds_available,
            self.lineup_available,
            self.injury_data_available,
            self.news_signals_available,
        ])

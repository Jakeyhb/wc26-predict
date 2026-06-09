"""LeakageGuard — prevent temporal data leakage in market calibration.

Rules (from action plan section 5.7):
  - T-24h predictions can only use odds captured at <= kickoff - 24h
  - T-6h predictions can only use odds captured at <= kickoff - 6h
  - T-90m predictions can only use odds captured at <= kickoff - 90m
  - Closing odds can only be used for benchmark, never for live prediction training
  - Train/val/test splits must be temporal, not random
"""
from __future__ import annotations
import logging

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


class PredictionWindow(Enum):
    """When the prediction is made relative to kickoff."""

    T_MINUS_24H = "t-24h"
    T_MINUS_6H = "t-6h"
    T_MINUS_90M = "t-90m"
    T_MINUS_40M = "t-40m"
    KICKOFF = "kickoff"
    POST_MATCH = "post_match"  # Used only for evaluation, never for prediction


# ── Allowed windows for each prediction horizon ──
_ALLOWED_MAP: dict[PredictionWindow, timedelta] = {
    PredictionWindow.T_MINUS_24H: timedelta(hours=24),
    PredictionWindow.T_MINUS_6H: timedelta(hours=6),
    PredictionWindow.T_MINUS_90M: timedelta(minutes=90),
    PredictionWindow.T_MINUS_40M: timedelta(minutes=40),
    PredictionWindow.KICKOFF: timedelta(minutes=0),
    PredictionWindow.POST_MATCH: timedelta(minutes=0),  # post-match uses closing odds
}


@dataclass
class LeakageCheckResult:
    """Result of a leakage check for a single odds data point."""

    allowed: bool
    reason: str = ""
    odds_captured_at: datetime | None = None
    kickoff_at: datetime | None = None
    prediction_window: PredictionWindow | None = None


class LeakageGuard:
    """Ensures temporal data integrity for market calibration.

    Prevents:
    1. Using odds captured after the prediction time
    2. Using closing odds for live prediction
    3. Using post-kickoff odds for pre-match predictions
    """

    @staticmethod
    def validate(
        odds_captured_at: datetime,
        kickoff_at: datetime,
        prediction_window: PredictionWindow,
        is_closing: bool = False,
    ) -> LeakageCheckResult:
        """Check if odds data can be used for a given prediction window.

        Args:
            odds_captured_at: When the odds were fetched from the provider.
            kickoff_at: Match kickoff time (UTC).
            prediction_window: When the prediction is made relative to kickoff.
            is_closing: Whether these are closing odds (T-0 odds).

        Returns:
            LeakageCheckResult with allowed=True if safe to use.
        """
        # Post-match evaluation can use anything
        if prediction_window == PredictionWindow.POST_MATCH:
            return LeakageCheckResult(
                allowed=True,
                reason="post-match evaluation has no leakage constraint",
                odds_captured_at=odds_captured_at,
                kickoff_at=kickoff_at,
                prediction_window=prediction_window,
            )

        # Closing odds must NOT be used for pre-match prediction
        if is_closing and prediction_window != PredictionWindow.POST_MATCH:
            return LeakageCheckResult(
                allowed=False,
                reason="closing odds cannot be used for pre-match predictions",
                odds_captured_at=odds_captured_at,
                kickoff_at=kickoff_at,
                prediction_window=prediction_window,
            )

        # Odds must be captured BEFORE kickoff
        if odds_captured_at >= kickoff_at:
            return LeakageCheckResult(
                allowed=False,
                reason=f"odds captured at {odds_captured_at.isoformat()} is after kickoff {kickoff_at.isoformat()}",
                odds_captured_at=odds_captured_at,
                kickoff_at=kickoff_at,
                prediction_window=prediction_window,
            )

        # Odds must be captured at least N hours before kickoff
        min_gap = _ALLOWED_MAP.get(prediction_window, timedelta(hours=24))
        effective_prediction_time = kickoff_at - min_gap
        if odds_captured_at > effective_prediction_time:
            return LeakageCheckResult(
                allowed=False,
                reason=(
                    f"odds captured at {odds_captured_at.isoformat()} is too late "
                    f"for {prediction_window.value} prediction (must be <= "
                    f"{effective_prediction_time.isoformat()})"
                ),
                odds_captured_at=odds_captured_at,
                kickoff_at=kickoff_at,
                prediction_window=prediction_window,
            )

        return LeakageCheckResult(
            allowed=True,
            reason="ok",
            odds_captured_at=odds_captured_at,
            kickoff_at=kickoff_at,
            prediction_window=prediction_window,
        )

    @staticmethod
    def get_latest_allowed_capture_time(
        kickoff_at: datetime,
        prediction_window: PredictionWindow,
    ) -> datetime:
        """Return the latest time odds can be captured for a given window."""
        if prediction_window == PredictionWindow.POST_MATCH:
            return kickoff_at + timedelta(days=365)  # any time post-match
        min_gap = _ALLOWED_MAP.get(prediction_window, timedelta(hours=24))
        return kickoff_at - min_gap

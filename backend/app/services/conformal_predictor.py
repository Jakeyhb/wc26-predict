"""WeightedConformalPredictor — prediction sets with coverage guarantee.

Follows the ``fit()`` / ``predict()`` / ``save()`` / ``load()`` service
interface pattern established by ``IsotonicCalibrator``.

"Fit" here means storing calibration records — no model training happens.
Prediction sets are computed lazily from the stored records at predict time.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.conformal_core import (
    nonconformity_score,
    recency_weight,
    compute_prediction_set,
    CONFORMAL_ALPHA,
    CONFORMAL_RECENCY_HALFLIFE_DAYS,
    CONFORMAL_MIN_CALIBRATION_SIZE,
)

logger = logging.getLogger(__name__)

OUTCOME_LABELS = ["home_win_prob", "draw_prob", "away_win_prob"]


@dataclass
class CalibrationRecord:
    """One calibration example: predicted probs + date + actual outcome."""

    probs: dict[str, float]            # {home_win_prob, draw_prob, away_win_prob}
    actual_result: str                 # "H", "D", or "A"
    match_date: str = ""               # ISO-format date for recency weighting

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CalibrationRecord":
        return cls(
            probs={
                "home_win_prob": float(data.get("home_win_prob", 1 / 3)),
                "draw_prob": float(data.get("draw_prob", 1 / 3)),
                "away_win_prob": float(data.get("away_win_prob", 1 / 3)),
            },
            actual_result=str(data.get("actual_result", "")),
            match_date=str(data.get("match_date", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "home_win_prob": self.probs["home_win_prob"],
            "draw_prob": self.probs["draw_prob"],
            "away_win_prob": self.probs["away_win_prob"],
            "actual_result": self.actual_result,
            "match_date": self.match_date,
        }


class WeightedConformalPredictor:
    """Weighted conformal prediction with exponential recency weighting.

    Stores a calibration set of (probability, outcome) pairs and computes
    conformal prediction sets on-the-fly at predict time.
    """

    def __init__(self) -> None:
        self.calibration_records: list[CalibrationRecord] = []
        self.is_fitted: bool = False
        self.fitted_at: datetime | None = None
        self.alpha: float = CONFORMAL_ALPHA
        self.halflife_days: float = CONFORMAL_RECENCY_HALFLIFE_DAYS

    # ── Fit (store calibration records) ──────────────────────────────

    def fit(self, records: list[CalibrationRecord]) -> "WeightedConformalPredictor":
        """Store calibration records.

        "Fit" is a misnomer carried over from the calibrator interface —
        no model training happens here.  Records are simply stored for
        later use by ``predict()``.
        """
        self.calibration_records = list(records)
        self.is_fitted = len(self.calibration_records) >= CONFORMAL_MIN_CALIBRATION_SIZE
        if self.is_fitted:
            self.fitted_at = datetime.now(timezone.utc)
        logger.info(
            "ConformalPredictor: stored %d calibration records (is_fitted=%s)",
            len(self.calibration_records), self.is_fitted,
        )
        return self

    def fit_from_records(
        self, records: list[dict[str, Any]]
    ) -> "WeightedConformalPredictor":
        """Convenience wrapper: parse dicts into CalibrationRecords, then fit."""
        parsed = [CalibrationRecord.from_dict(r) for r in records]
        return self.fit(parsed)

    # ── Predict ──────────────────────────────────────────────────────

    def predict(
        self,
        probs: dict[str, float],
        as_of: str = "",
    ) -> dict[str, Any]:
        """Compute conformal prediction set for one forecast.

        Args:
            probs: Fused H/D/A probabilities with keys ``home_win_prob``,
                ``draw_prob``, ``away_win_prob``.
            as_of: ISO-format timestamp for recency weighting (e.g.
                ``"2026-07-01T20:00:00Z"``).  When empty, uniform weights
                are used.

        Returns:
            Dict with ``prediction_set`` (list[int]), ``adjusted_probs``
            (list[float]), ``threshold``, ``coverage``, ``set_size``.
        """
        if not self.is_fitted:
            return {
                "prediction_set": [0, 1, 2],
                "adjusted_probs": [
                    float(probs.get("home_win_prob", 1 / 3)),
                    float(probs.get("draw_prob", 1 / 3)),
                    float(probs.get("away_win_prob", 1 / 3)),
                ],
                "threshold": 1.0,
                "coverage": 1.0 - self.alpha,
                "set_size": 3,
                "applied": False,
                "reason": "not_fitted",
            }

        class_probs = [
            float(probs.get("home_win_prob", 1 / 3)),
            float(probs.get("draw_prob", 1 / 3)),
            float(probs.get("away_win_prob", 1 / 3)),
        ]

        # Compute nonconformity scores and recency weights for calibration set
        cal_scores: list[float] = []
        cal_weights: list[float] = []

        # Parse as_of timestamp for recency weighting
        as_of_ts = _parse_timestamp(as_of) if as_of else 0.0

        for rec in self.calibration_records:
            # Nonconformity score: 1 − P(actual outcome)
            if rec.actual_result == "H":
                p_true = rec.probs["home_win_prob"]
            elif rec.actual_result == "A":
                p_true = rec.probs["away_win_prob"]
            else:
                p_true = rec.probs["draw_prob"]
            cal_scores.append(nonconformity_score(p_true))

            # Recency weight
            if as_of_ts > 0 and rec.match_date:
                cal_ts = _parse_timestamp(rec.match_date)
                cal_weights.append(recency_weight(as_of_ts, cal_ts, self.halflife_days))
            else:
                cal_weights.append(1.0)

        result = compute_prediction_set(
            class_probs=class_probs,
            calibration_scores=cal_scores,
            calibration_weights=cal_weights,
            alpha=self.alpha,
        )

        # Add human-readable outcome labels
        idx_to_label = {0: "home", 1: "draw", 2: "away"}
        result["prediction_labels"] = [
            idx_to_label.get(i, f"class_{i}") for i in result["prediction_set"]
        ]
        result["applied"] = True
        result["calibration_size"] = len(self.calibration_records)

        return result

    # ── Serialization ────────────────────────────────────────────────

    def save(self, path: str) -> None:
        """Save calibration records as JSON."""
        payload: dict[str, Any] = {
            "alpha": self.alpha,
            "halflife_days": self.halflife_days,
            "is_fitted": self.is_fitted,
            "fitted_at": self.fitted_at.isoformat() if self.fitted_at else None,
            "calibration_records": [r.to_dict() for r in self.calibration_records],
        }
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, path: str) -> None:
        """Load calibration records from JSON."""
        target = Path(path)
        if not target.exists():
            self.__init__()
            return

        payload = json.loads(target.read_text(encoding="utf-8"))
        self.alpha = float(payload.get("alpha", CONFORMAL_ALPHA))
        self.halflife_days = float(
            payload.get("halflife_days", CONFORMAL_RECENCY_HALFLIFE_DAYS)
        )
        self.is_fitted = bool(payload.get("is_fitted", False))
        fitted_at = payload.get("fitted_at")
        self.fitted_at = datetime.fromisoformat(fitted_at) if fitted_at else None
        self.calibration_records = [
            CalibrationRecord.from_dict(r)
            for r in payload.get("calibration_records", [])
        ]

    # ── Diagnostics ──────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Return calibration metadata for pipeline logging."""
        return {
            "is_fitted": self.is_fitted,
            "calibration_size": len(self.calibration_records),
            "fitted_at": self.fitted_at.isoformat() if self.fitted_at else None,
            "alpha": self.alpha,
            "halflife_days": self.halflife_days,
            "nominal_coverage": 1.0 - self.alpha,
        }


# ── Helper ──────────────────────────────────────────────────────────────

def _parse_timestamp(iso_string: str) -> float:
    """Parse an ISO-8601 string into a Unix timestamp (float seconds).

    Returns 0.0 on failure.
    """
    try:
        # Handle various ISO formats
        s = iso_string.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return 0.0

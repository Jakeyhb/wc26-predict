from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


CALIBRATION_KEYS = {
    "home_win": "home_win_prob",
    "draw": "draw_prob",
    "away_win": "away_win_prob",
}


@dataclass
class CalibrationCurve:
    x_thresholds: list[float]
    y_thresholds: list[float]

    def predict(self, value: float) -> float:
        if not self.x_thresholds or not self.y_thresholds:
            return float(value)
        clipped = float(np.clip(value, 0.0, 1.0))
        if len(self.x_thresholds) == 1:
            return float(np.clip(self.y_thresholds[0], 0.0, 1.0))
        return float(
            np.interp(
                clipped,
                np.asarray(self.x_thresholds, dtype=float),
                np.asarray(self.y_thresholds, dtype=float),
                left=self.y_thresholds[0],
                right=self.y_thresholds[-1],
            )
        )


class IsotonicCalibrator:
    """
    对Dixon-Coles输出的原始概率进行保序回归校准。
    """

    def __init__(self) -> None:
        self.calibrators: dict[str, CalibrationCurve | None] = {
            "home_win": None,
            "draw": None,
            "away_win": None,
        }
        self.is_fitted = False
        self.fitted_at: datetime | None = None
        self.training_sample_count = 0
        self._expected_calibration_error = 0.0

    def fit_from_db_records(self, eval_records: list[dict[str, Any]]) -> "IsotonicCalibrator":
        self.calibrators = {key: None for key in self.calibrators}
        self.is_fitted = False
        self.fitted_at = None
        self.training_sample_count = len(eval_records)
        self._expected_calibration_error = 0.0

        if len(eval_records) < 20:
            return self

        try:
            from sklearn.isotonic import IsotonicRegression
        except Exception:
            return self

        ece_values: list[float] = []
        for key, prob_field in CALIBRATION_KEYS.items():
            x = np.asarray([float(record.get(prob_field, 0.0)) for record in eval_records], dtype=float)
            y = np.asarray(
                [
                    1.0
                    if (
                        (record.get("actual_result") == "H" and key == "home_win")
                        or (record.get("actual_result") == "D" and key == "draw")
                        or (record.get("actual_result") == "A" and key == "away_win")
                    )
                    else 0.0
                    for record in eval_records
                ],
                dtype=float,
            )
            calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            calibrator.fit(x, y)
            curve = CalibrationCurve(
                x_thresholds=[float(item) for item in calibrator.X_thresholds_.tolist()],
                y_thresholds=[float(item) for item in calibrator.y_thresholds_.tolist()],
            )
            self.calibrators[key] = curve
            ece_values.append(self._estimate_ece(x, np.asarray([curve.predict(value) for value in x], dtype=float), y))

        self.is_fitted = any(curve is not None for curve in self.calibrators.values())
        if self.is_fitted:
            self.fitted_at = datetime.now(timezone.utc)
            self._expected_calibration_error = float(sum(ece_values) / len(ece_values)) if ece_values else 0.0
        return self

    def calibrate(self, raw_probs: dict[str, float]) -> dict[str, float]:
        normalized = self._normalize_output(
            {
                "home_win_prob": float(raw_probs.get("home_win_prob", 0.0)),
                "draw_prob": float(raw_probs.get("draw_prob", 0.0)),
                "away_win_prob": float(raw_probs.get("away_win_prob", 0.0)),
            }
        )
        if not self.is_fitted:
            return normalized

        calibrated = {}
        for key, prob_field in CALIBRATION_KEYS.items():
            curve = self.calibrators.get(key)
            value = normalized[prob_field]
            calibrated[prob_field] = curve.predict(value) if curve is not None else value
        return self._normalize_output(calibrated)

    def save(self, path: str) -> None:
        payload = {
            "is_fitted": self.is_fitted,
            "fitted_at": self.fitted_at.isoformat() if self.fitted_at else None,
            "training_sample_count": self.training_sample_count,
            "expected_calibration_error": self._expected_calibration_error,
            "calibrators": {
                key: (
                    {
                        "x_thresholds": curve.x_thresholds,
                        "y_thresholds": curve.y_thresholds,
                    }
                    if curve is not None
                    else None
                )
                for key, curve in self.calibrators.items()
            },
        }
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, path: str) -> None:
        target = Path(path)
        if not target.exists():
            self.__init__()
            return
        payload = json.loads(target.read_text(encoding="utf-8"))
        self.is_fitted = bool(payload.get("is_fitted"))
        fitted_at = payload.get("fitted_at")
        self.fitted_at = datetime.fromisoformat(fitted_at) if fitted_at else None
        self.training_sample_count = int(payload.get("training_sample_count", 0))
        self._expected_calibration_error = float(payload.get("expected_calibration_error", 0.0))
        calibrators = payload.get("calibrators", {})
        self.calibrators = {
            key: (
                CalibrationCurve(
                    x_thresholds=[float(item) for item in curve_payload.get("x_thresholds", [])],
                    y_thresholds=[float(item) for item in curve_payload.get("y_thresholds", [])],
                )
                if curve_payload
                else None
            )
            for key, curve_payload in calibrators.items()
        }

    def calibration_stats(self) -> dict[str, Any]:
        return {
            "is_fitted": self.is_fitted,
            "training_samples": self.training_sample_count,
            "fitted_at": self.fitted_at.isoformat() if self.fitted_at else None,
            "expected_calibration_error": self._expected_calibration_error,
        }

    def _normalize_output(self, probs: dict[str, float]) -> dict[str, float]:
        safe = {key: float(np.clip(value, 0.0, 1.0)) for key, value in probs.items()}
        total = sum(safe.values())
        if total <= 0:
            return {
                "home_win_prob": 1 / 3,
                "draw_prob": 1 / 3,
                "away_win_prob": 1 / 3,
            }
        return {key: value / total for key, value in safe.items()}

    def _estimate_ece(self, raw_probs: np.ndarray, calibrated_probs: np.ndarray, labels: np.ndarray, bins: int = 10) -> float:
        if len(raw_probs) == 0:
            return 0.0
        bucket_edges = np.linspace(0.0, 1.0, bins + 1)
        ece = 0.0
        total = len(raw_probs)
        for index in range(bins):
            lower = bucket_edges[index]
            upper = bucket_edges[index + 1]
            if index == bins - 1:
                mask = (raw_probs >= lower) & (raw_probs <= upper)
            else:
                mask = (raw_probs >= lower) & (raw_probs < upper)
            if not np.any(mask):
                continue
            avg_confidence = float(np.mean(calibrated_probs[mask]))
            avg_accuracy = float(np.mean(labels[mask]))
            ece += abs(avg_confidence - avg_accuracy) * (int(np.sum(mask)) / total)
        return float(ece)

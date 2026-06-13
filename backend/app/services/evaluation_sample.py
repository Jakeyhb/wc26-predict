"""Shared evaluation-sample helpers for paired walk-forward benchmarks."""

from __future__ import annotations

import math
from typing import Any


EVALUATION_SAMPLE_SCHEMA_VERSION = "v1"
EVALUATION_CANDIDATE_LABELS = (
    "current_fusion",
    "snapshot_adjusted",
    "snapshot_baseline",
    "dc_only",
    "tabular_only",
    "elo_only",
    "pi_only",
    "weibull_only",
    "market_only",
    "uniform_baseline",
)
UNIFORM_PROBS = {"home": 1 / 3, "draw": 1 / 3, "away": 1 / 3}


def normalize_1x2_payload(raw: Any) -> dict[str, float] | None:
    """Return normalized {home, draw, away} probabilities or None."""
    if not isinstance(raw, dict):
        return None
    values = {
        "home": raw.get("home", raw.get("home_win_prob", raw.get("home_prob"))),
        "draw": raw.get("draw", raw.get("draw_prob")),
        "away": raw.get("away", raw.get("away_win_prob", raw.get("away_prob"))),
    }
    try:
        home = float(values["home"])
        draw = float(values["draw"])
        away = float(values["away"])
    except (TypeError, ValueError):
        return None
    probs = [home, draw, away]
    if any((not math.isfinite(item)) or item < 0 for item in probs):
        return None
    total = sum(probs)
    if total <= 0:
        return None
    return {
        "home": home / total,
        "draw": draw / total,
        "away": away / total,
    }


def build_evaluation_sample(
    *,
    match_id: str,
    as_of_time: str,
    generated_at: str,
    model_version: str,
    weight_label: str,
    raw_candidates: dict[str, Any],
    schema_version: str = EVALUATION_SAMPLE_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Build a stable evaluation sample without inventing missing candidates."""
    candidate_probs: dict[str, dict[str, float]] = {}
    candidate_status: dict[str, dict[str, str]] = {}

    for label in EVALUATION_CANDIDATE_LABELS:
        normalized = normalize_1x2_payload(raw_candidates.get(label))
        if normalized is None:
            candidate_status[label] = {
                "status": "missing",
                "reason": "missing_or_invalid_probs",
            }
            continue
        candidate_probs[label] = normalized
        candidate_status[label] = {
            "status": "available",
            "reason": "",
        }

    return {
        "schema_version": schema_version,
        "match_id": str(match_id or ""),
        "as_of_time": str(as_of_time or ""),
        "generated_at": str(generated_at or ""),
        "model_version": str(model_version or ""),
        "weight_label": str(weight_label or ""),
        "candidate_probs": candidate_probs,
        "candidate_status": candidate_status,
    }


def evaluation_sample_from_prediction_dict(result: dict[str, Any]) -> dict[str, Any]:
    """Build an evaluation sample from PredictionResult.to_dict() shape."""
    meta = result.get("meta") or {}
    prediction = result.get("prediction") or {}
    components = result.get("component_probs") or {}
    calibration_monitor = result.get("calibration_monitor") or {}
    weight_config = meta.get("weight_config") or {}

    final_probs = {
        "home": prediction.get("home_win_prob"),
        "draw": prediction.get("draw_prob"),
        "away": prediction.get("away_win_prob"),
    }
    raw_candidates = {
        "current_fusion": final_probs,
        "snapshot_adjusted": final_probs,
        "snapshot_baseline": calibration_monitor.get("baseline_probs"),
        "dc_only": components.get("dc") or components.get("dixon_coles"),
        "tabular_only": components.get("enhancer") or components.get("tabular"),
        "elo_only": components.get("elo"),
        "pi_only": components.get("pi_rating") or components.get("pi"),
        "weibull_only": components.get("weibull"),
        "market_only": components.get("market"),
        "uniform_baseline": UNIFORM_PROBS,
    }
    return build_evaluation_sample(
        match_id=str(meta.get("match_id") or ""),
        as_of_time=str(meta.get("as_of") or meta.get("generated_at") or ""),
        generated_at=str(meta.get("generated_at") or meta.get("as_of") or ""),
        model_version=str(meta.get("model_version") or ""),
        weight_label=str(weight_config.get("label") or ""),
        raw_candidates=raw_candidates,
    )

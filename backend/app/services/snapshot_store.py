"""Save prediction results as standardized PredictionSnapshot AND PredictionRun records.

Writes to both prediction_snapshots (script-side) and prediction_runs (API-side)
so that RPS optimizer and postmatch eval can find data regardless of entry point.
"""

from __future__ import annotations

import math
import uuid as _uuid
from datetime import datetime, timezone
from typing import Any

import numpy as np

from app.database import AsyncSessionLocal
from app.models.prediction_snapshot import PredictionSnapshot
from app.models.prediction_run import PredictionRun
from app.models.enums import PredictionRunType


async def save_prediction_snapshot(
    result: dict[str, Any],
    run_type: str = "baseline_v0",
    report_path: str | None = None,
    report_markdown: str | None = None,
) -> PredictionSnapshot:
    """Persist a prediction result as a standardized snapshot.

    Also writes a PredictionRun record so the RPS optimizer (optimize_weights.py)
    and Celery postmatch_eval tasks can find this prediction via prediction_runs.
    """
    m = result["meta"]
    p = result["prediction"]
    e = result["elo"]

    # Determine confidence level
    missing_count = len(result.get("missing_data", []))
    if missing_count <= 1:
        confidence = "medium"
    elif missing_count <= 3:
        confidence = "low"
    else:
        confidence = "low"

    # Rebuild score matrix from xG for prediction_runs compatibility
    score_matrix = _build_score_matrix(p["home_xg"], p["away_xg"])
    conf_score = 0.55
    cal_monitor = p.get("calibration_monitor", {})
    if cal_monitor and cal_monitor.get("baseline_probs"):
        conf_score = 0.65

    snapshot = PredictionSnapshot(
        match_id=m.get("match_id", ""),
        run_type=run_type,
        model_version="2.0.0",
        home_team=m["home_team"],
        away_team=m["away_team"],
        competition=m["competition"],
        match_time=m.get("match_date", None),
        baseline_probs={
            "home": p["home_win_prob"],
            "draw": p["draw_prob"],
            "away": p["away_win_prob"],
        },
        component_probs=result.get("component_probs"),
        market_probs=result.get("market_divergence", {}).get("applied") and {
            "home": result["market_divergence"].get("market_home_prob"),
        } or None,
        adjusted_probs={
            "home": p["home_win_prob"],
            "draw": p["draw_prob"],
            "away": p["away_win_prob"],
        },
        expected_goals={
            "home": p["home_xg"],
            "away": p["away_xg"],
        },
        top_scores=p.get("top3_scores", []),
        elo_ratings={
            "home": e["home_elo"],
            "away": e["away_elo"],
            "gap": e["rating_gap"],
            "k_factor": e["k_factor"],
        },
        active_event_ids=[],
        missing_inputs=[
            item["item"] for item in result.get("missing_data", [])
        ],
        confidence=confidence,
        calibration_monitor=p.get("calibration_monitor"),
        pipeline_params={
            "dc_converged": result["pipeline"].get("dc_converged"),
            "dc_nll": result["pipeline"].get("dc_nll"),
            "enhancer_algorithm": result["pipeline"].get("enhancer_algorithm"),
            "enhancer_rows": result["pipeline"].get("enhancer_rows"),
            "enhancer_features": result["pipeline"].get("enhancer_features"),
            "elo_matches": result["pipeline"].get("elo_matches"),
            "training_rows": m.get("training_rows"),
        },
        report_path=report_path,
        report_markdown=report_markdown,
    )

    async with AsyncSessionLocal() as db:
        db.add(snapshot)
        await db.commit()
        await db.refresh(snapshot)

    # Sync to prediction_runs (bridge for RPS optimizer + Celery tasks)
    await _sync_to_prediction_runs(result, run_type, score_matrix, conf_score)

    return snapshot


async def _sync_to_prediction_runs(
    result: dict[str, Any],
    run_type: str,
    score_matrix: list[list[float]],
    confidence_score: float,
) -> None:
    """Write a matching PredictionRun record so optimize_weights.py finds this prediction.

    Uses raw SQL to avoid ORM UUID conversion issues with CHAR(32) match_id format.
    """
    m = result["meta"]
    p = result["prediction"]
    adj = result.get("adjustment", {})
    risk_tags = adj.get("risk_tags", [])
    adjustment_log = adj.get("log", [])

    # Normalize match_id to UUID format (add dashes if missing)
    match_id_raw = m.get("match_id", "")
    match_uuid = _normalize_uuid(match_id_raw)

    # Map run_type string to PredictionRunType enum value
    run_type_map = {
        "baseline_v0": "MANUAL",
        "manual": "MANUAL",
        "t_minus_24h": "T_MINUS_24H",
        "t_minus_3h": "T_MINUS_3H",
        "t_lineup": "T_LINEUP",
    }
    prt_value = run_type_map.get(run_type, "MANUAL")

    # Build feature snapshot for audit trail
    feature_snapshot = {
        "training_rows": m.get("training_rows"),
        "match_context": {
            "home_team_name": m["home_team"],
            "away_team_name": m["away_team"],
            "competition": m["competition"],
            "is_neutral": m.get("is_neutral", False),
        },
        "adjustment_log": adjustment_log,
        "prediction_mode": "script_snapshot",
        "source": "snapshot.py -> save_prediction_snapshot()",
    }

    now_ts = datetime.now(timezone.utc).isoformat()
    pred_run_id = str(_uuid.uuid4())

    try:
        from sqlalchemy import text
        async with AsyncSessionLocal() as db:
            await db.execute(
                text(
                    "INSERT INTO prediction_runs "
                    "(id, match_id, run_type, model_version, as_of_time, "
                    " home_win_prob, draw_prob, away_win_prob, home_xg, away_xg, "
                    " score_matrix, top3_scores, confidence_score, risk_tags, "
                    " input_feature_snapshot, approved_signals, created_at) "
                    "VALUES ("
                    " :id, :match_id, :run_type, :model_version, :as_of_time, "
                    " :home_win_prob, :draw_prob, :away_win_prob, :home_xg, :away_xg, "
                    " :score_matrix, :top3_scores, :confidence_score, :risk_tags, "
                    " :feature_snapshot, :approved_signals, :created_at"
                    ")"
                ),
                {
                    "id": pred_run_id,
                    "match_id": match_uuid if match_uuid else pred_run_id,
                    "run_type": prt_value,
                    "model_version": "2.0.0",
                    "as_of_time": now_ts,
                    "home_win_prob": round(float(p["home_win_prob"]), 6),
                    "draw_prob": round(float(p["draw_prob"]), 6),
                    "away_win_prob": round(float(p["away_win_prob"]), 6),
                    "home_xg": round(float(p["home_xg"]), 4),
                    "away_xg": round(float(p["away_xg"]), 4),
                    "score_matrix": _json_dumps(score_matrix),
                    "top3_scores": _json_dumps(p.get("top3_scores", [])),
                    "confidence_score": round(float(confidence_score), 4),
                    "risk_tags": _json_dumps(risk_tags),
                    "feature_snapshot": _json_dumps(feature_snapshot),
                    "approved_signals": _json_dumps([]),
                    "created_at": now_ts,
                },
            )
            await db.commit()
    except Exception:
        # prediction_runs sync is best-effort; never break the main pipeline
        pass


def _normalize_uuid(raw: str) -> str | None:
    """Convert a 32-char hex string to UUID format with dashes."""
    if not raw:
        return None
    clean = raw.replace("-", "").strip()
    if len(clean) != 32:
        return None
    return f"{clean[:8]}-{clean[8:12]}-{clean[12:16]}-{clean[16:20]}-{clean[20:]}"


def _build_score_matrix(home_xg: float, away_xg: float, max_goals: int = 5) -> list[list[float]]:
    """Reconstruct Poisson score probability matrix from xG values."""
    def _poisson_pmf(goals: int, rate: float) -> float:
        rate = max(float(rate), 1e-8)
        return math.exp(goals * math.log(rate) - rate - math.lgamma(goals + 1))

    size = max_goals + 1
    matrix = np.zeros((size, size))
    for hg in range(size):
        for ag in range(size):
            matrix[hg, ag] = _poisson_pmf(hg, float(home_xg)) * _poisson_pmf(ag, float(away_xg))
    total = float(matrix.sum())
    if total > 0:
        matrix = matrix / total
    return matrix.tolist()


def _json_dumps(obj: Any) -> str:
    """JSON-serialize an object to string for raw SQL insertion."""
    import json
    return json.dumps(obj, ensure_ascii=False, default=str)

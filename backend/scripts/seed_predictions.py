from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import selectinload

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import AsyncSessionLocal
from app.logging import configure_logging
from app.models import Match, PostmatchEval, PredictionRun
from app.models.enums import MatchResultCode, MatchStatus, PredictionRunType
from app.services.calibration import IsotonicCalibrator
from app.services.dixon_coles import DixonColesModel, load_training_frame, WC26_FIFA_TIERS
from app.services.tabular_match_model import TabularMatchEnhancer
from app.services.tabular_match_model import fuse_outcome_probabilities


def _matches_to_frame(matches: list[Match]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for match in matches:
        if match.result is None or match.home_team is None or match.away_team is None:
            continue
        rows.append(
            {
                "match_date": match.match_date,
                "home_team": match.home_team.name,
                "away_team": match.away_team.name,
                "home_goals": match.result.home_goals,
                "away_goals": match.result.away_goals,
                "competition_weight": match.competition_weight,
                "is_neutral_venue": match.is_neutral_venue,
                "home_xg": match.result.home_xg,
                "away_xg": match.result.away_xg,
            }
        )
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame["match_date"] = pd.to_datetime(frame["match_date"], utc=True)
        frame = frame.sort_values("match_date").reset_index(drop=True)
    return frame


def _build_postmatch_eval(run: PredictionRun) -> PostmatchEval:
    result = run.match.result
    if result is None:
        raise RuntimeError(f"Match {run.match_id} has no result")

    actual_index = 0 if result.home_goals > result.away_goals else 1 if result.home_goals == result.away_goals else 2
    probs = [run.home_win_prob, run.draw_prob, run.away_win_prob]
    actual = [0.0, 0.0, 0.0]
    actual[actual_index] = 1.0
    brier = sum((prob - observed) ** 2 for prob, observed in zip(probs, actual, strict=False))
    exact_score = f"{result.home_goals}:{result.away_goals}"

    import math

    return PostmatchEval(
        prediction_run_id=run.id,
        actual_home_goals=result.home_goals,
        actual_away_goals=result.away_goals,
        actual_result=MatchResultCode.HOME if actual_index == 0 else MatchResultCode.DRAW if actual_index == 1 else MatchResultCode.AWAY,
        brier_score=brier,
        log_loss=-math.log(max(probs[actual_index], 1e-12)),
        exact_score_hit=bool(run.top3_scores and run.top3_scores[0]["score"] == exact_score),
        top3_hit=any(item["score"] == exact_score for item in run.top3_scores),
        calibration_bucket=min(10, max(1, int(max(probs) * 10) + 1)),
        notes="Seeded from 2022 World Cup group stage backtest",
    )


def _ece(records: list[dict[str, object]], key: str, bins: int = 10) -> float:
    if not records:
        return 0.0
    import numpy as np

    field = f"{key}_prob"
    raw_probs = np.asarray([float(record[field]) for record in records], dtype=float)
    labels = np.asarray(
        [
            1.0
            if (
                (record["actual_result"] == "H" and key == "home_win")
                or (record["actual_result"] == "D" and key == "draw")
                or (record["actual_result"] == "A" and key == "away_win")
            )
            else 0.0
            for record in records
        ],
        dtype=float,
    )
    bucket_edges = np.linspace(0.0, 1.0, bins + 1)
    error = 0.0
    for index in range(bins):
        lower = bucket_edges[index]
        upper = bucket_edges[index + 1]
        upper_mask = raw_probs <= upper if index == bins - 1 else raw_probs < upper
        mask = (raw_probs >= lower) & upper_mask
        if not np.any(mask):
            continue
        confidence = float(np.mean(raw_probs[mask]))
        accuracy = float(np.mean(labels[mask]))
        error += abs(confidence - accuracy) * (int(np.sum(mask)) / len(records))
    return float(error)


def _brier(records: list[dict[str, object]]) -> float:
    if not records:
        return 0.0
    total = 0.0
    for record in records:
        actual = [
            1.0 if record["actual_result"] == "H" else 0.0,
            1.0 if record["actual_result"] == "D" else 0.0,
            1.0 if record["actual_result"] == "A" else 0.0,
        ]
        probs = [float(record["home_win_prob"]), float(record["draw_prob"]), float(record["away_win_prob"])]
        total += sum((prob - observed) ** 2 for prob, observed in zip(probs, actual, strict=False)) / 3
    return total / len(records)


async def run() -> None:
    group_stage_start = datetime(2022, 11, 20, tzinfo=UTC)
    group_stage_end = datetime(2022, 12, 2, 23, 59, 59, tzinfo=UTC)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Match)
            .options(selectinload(Match.home_team), selectinload(Match.away_team), selectinload(Match.result))
            .where(
                Match.status == MatchStatus.FINISHED,
                Match.competition.ilike("%World Cup%"),
                Match.match_date >= group_stage_start,
                Match.match_date <= group_stage_end,
            )
            .order_by(Match.match_date.asc())
        )
        group_matches = result.scalars().unique().all()

        if len(group_matches) < 48:
            raise RuntimeError(f"Expected at least 48 group-stage matches from 2022 World Cup, found {len(group_matches)}")

        group_matches = group_matches[:48]
        train_matches = group_matches[:32]
        eval_matches = group_matches[32:48]

        training_df = _matches_to_frame(train_matches)
        if len(training_df) < 32:
            raise RuntimeError("Training set for seed predictions is incomplete.")

        # Build minimal team_info from training data teams
        team_info = {}
        for team_name in set(training_df["home_team"]).union(training_df["away_team"]):
            team_info[team_name] = {"confederation": "FIFA", "fifa_tier": WC26_FIFA_TIERS.get(team_name, 0)}
        model = DixonColesModel()
        model.set_team_info(team_info)
        fit_summary = model.fit(training_df)
        enhancer = TabularMatchEnhancer()
        enhancer_summary = enhancer.fit(training_df)
        print("Seed model fit summary:")
        print(asdict(fit_summary))
        print("Seed tabular enhancer fit summary:")
        print(asdict(enhancer_summary))

        rolling_history = training_df.copy()
        for match in eval_matches:
            existing_run_result = await db.execute(
                select(PredictionRun)
                .options(selectinload(PredictionRun.match).selectinload(Match.result))
                .where(
                    PredictionRun.match_id == match.id,
                    PredictionRun.run_type == PredictionRunType.T_MINUS_24H,
                    PredictionRun.model_version == "dc_seed_v1",
                )
                .order_by(PredictionRun.created_at.desc())
                .limit(1)
            )
            run = existing_run_result.scalars().first()
            if run is None:
                base_prediction = model.predict_match(
                    match.home_team.name,
                    match.away_team.name,
                    is_neutral_venue=match.is_neutral_venue,
                )
                rest_days = {
                    "home": _days_since_last_match(match.home_team.name, rolling_history, match.match_date),
                    "away": _days_since_last_match(match.away_team.name, rolling_history, match.match_date),
                }
                enhancer_prediction = enhancer.predict_match(
                    home_team=match.home_team.name,
                    away_team=match.away_team.name,
                    match_date=match.match_date,
                    competition_weight=match.competition_weight,
                    is_neutral_venue=match.is_neutral_venue,
                    training_df=rolling_history,
                    rest_days=rest_days,
                )
                probabilities = fuse_outcome_probabilities(
                    {
                        "home_win_prob": float(base_prediction["home_win_prob"]),
                        "draw_prob": float(base_prediction["draw_prob"]),
                        "away_win_prob": float(base_prediction["away_win_prob"]),
                    },
                    {
                        "home_win_prob": float(enhancer_prediction["home_win_prob"]),
                        "draw_prob": float(enhancer_prediction["draw_prob"]),
                        "away_win_prob": float(enhancer_prediction["away_win_prob"]),
                    },
                    base_weight=0.68,
                )
                margin = abs(probabilities["home_win_prob"] - probabilities["away_win_prob"])
                run = PredictionRun(
                    match_id=match.id,
                    run_type=PredictionRunType.T_MINUS_24H,
                    model_version="dc_tabular_seed_v1",
                    as_of_time=match.match_date - timedelta(hours=24),
                    home_win_prob=probabilities["home_win_prob"],
                    draw_prob=probabilities["draw_prob"],
                    away_win_prob=probabilities["away_win_prob"],
                    home_xg=base_prediction["home_xg"],
                    away_xg=base_prediction["away_xg"],
                    score_matrix=base_prediction["score_matrix"],
                    top3_scores=base_prediction["top3_scores"],
                    confidence_score=min(0.9, 0.52 + margin * 0.35),
                    risk_tags=[],
                    input_feature_snapshot={
                        "seed_script": "seed_predictions.py",
                        "training_rows": len(rolling_history),
                        "fit_summary": asdict(fit_summary),
                        "enhancer_fit_summary": asdict(enhancer_summary),
                        "enhancer_features": enhancer_prediction["feature_snapshot"],
                        "ensemble": {
                            "dixon_weight": 0.68,
                            "enhancer_weight": 0.32,
                        },
                    },
                    approved_signals=[],
                )
                run.match = match
                db.add(run)
                await db.flush()

            existing_eval_result = await db.execute(
                select(PostmatchEval).where(PostmatchEval.prediction_run_id == run.id).limit(1)
            )
            if existing_eval_result.scalar_one_or_none() is None:
                db.add(_build_postmatch_eval(run))

            match_frame = _matches_to_frame([match])
            match_timestamp = _as_utc_timestamp(match.match_date)
            if not match_frame.empty and (
                rolling_history.empty or not (
                    (rolling_history["home_team"] == match.home_team.name)
                    & (rolling_history["away_team"] == match.away_team.name)
                    & (pd.to_datetime(rolling_history["match_date"], utc=True) == match_timestamp)
                ).any()
            ):
                rolling_history = pd.concat(
                    [rolling_history, match_frame],
                    ignore_index=True,
                ).sort_values("match_date").reset_index(drop=True)

        await db.commit()

        eval_result = await db.execute(
            select(PostmatchEval)
            .join(PredictionRun, PredictionRun.id == PostmatchEval.prediction_run_id)
            .where(
                PredictionRun.model_version == "dc_tabular_seed_v1",
                PredictionRun.run_type == PredictionRunType.T_MINUS_24H,
                PredictionRun.match_id.in_([match.id for match in eval_matches]),
            )
        )
        evaluations = eval_result.scalars().all()

        seeded_run_result = await db.execute(
            select(PredictionRun, PostmatchEval)
            .join(PostmatchEval, PostmatchEval.prediction_run_id == PredictionRun.id)
            .where(
                PredictionRun.model_version == "dc_tabular_seed_v1",
                PredictionRun.run_type == PredictionRunType.T_MINUS_24H,
                PredictionRun.match_id.in_([match.id for match in eval_matches]),
            )
        )
        eval_records = [
            {
                "home_win_prob": run.home_win_prob,
                "draw_prob": run.draw_prob,
                "away_win_prob": run.away_win_prob,
                "actual_result": evaluation.actual_result,
            }
            for run, evaluation in seeded_run_result.all()
        ]

        calibration_records_result = await db.execute(
            select(PredictionRun, PostmatchEval)
            .join(PostmatchEval, PostmatchEval.prediction_run_id == PredictionRun.id)
            .order_by(PostmatchEval.created_at.asc())
        )
        calibration_records = [
            {
                "home_win_prob": run.home_win_prob,
                "draw_prob": run.draw_prob,
                "away_win_prob": run.away_win_prob,
                "actual_result": evaluation.actual_result,
            }
            for run, evaluation in calibration_records_result.all()
        ]

    if not evaluations:
        raise RuntimeError("No seeded evaluations were created.")

    avg_brier = sum(item.brier_score for item in evaluations) / len(evaluations)
    top3_hit_rate = sum(1 for item in evaluations if item.top3_hit) / len(evaluations)
    ece_before = sum(_ece(eval_records, key) for key in ("home_win", "draw", "away_win")) / 3
    calibrator = IsotonicCalibrator().fit_from_db_records(calibration_records)
    if calibrator.is_fitted:
        calibrated_eval_records = []
        for record in eval_records:
            calibrated_probs = calibrator.calibrate(
                {
                    "home_win_prob": float(record["home_win_prob"]),
                    "draw_prob": float(record["draw_prob"]),
                    "away_win_prob": float(record["away_win_prob"]),
                }
            )
            calibrated_eval_records.append({**record, **calibrated_probs})
        ece_after = sum(_ece(calibrated_eval_records, key) for key in ("home_win", "draw", "away_win")) / 3
        brier_after = _brier(calibrated_eval_records)
    else:
        calibrated_eval_records = []
        ece_after = None
        brier_after = None
    print(f"Seeded {len(evaluations)} postmatch evaluations")
    print(f"Overall Brier Score: {avg_brier:.6f}")
    print(f"Top3 Hit Rate: {top3_hit_rate:.4f}")
    print(f"ECE before calibration: {ece_before:.6f}")
    if calibrator.is_fitted and ece_after is not None and brier_after is not None:
        print(f"Brier Score after calibration: {brier_after:.6f}")
        print(f"ECE after calibration: {ece_after:.6f}")
    else:
        print("Calibration skipped: available postmatch records fewer than 20")


def main() -> None:
    configure_logging()
    asyncio.run(run())


def _days_since_last_match(team_name: str, history_df: pd.DataFrame, match_date: datetime) -> int | None:
    if history_df.empty:
        return None
    team_history = history_df[(history_df["home_team"] == team_name) | (history_df["away_team"] == team_name)]
    if team_history.empty:
        return None
    previous = pd.to_datetime(team_history["match_date"], utc=True).max()
    target = _as_utc_timestamp(match_date)
    return max(0, int((target - previous).days))


def _as_utc_timestamp(value: datetime) -> pd.Timestamp:
    target = pd.Timestamp(value)
    if target.tzinfo is None:
        target = target.tz_localize("UTC")
    else:
        target = target.tz_convert("UTC")
    return target


if __name__ == "__main__":
    main()

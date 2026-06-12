#!/usr/bin/env python3
"""Read-only walk-forward evaluation over stored predictions.

This is the first release-gate scaffold: it evaluates only predictions whose
as_of_time/generated_at is not after kickoff, then reports proper scoring
metrics by model/baseline, horizon, run type, and competition. It does not
retrain models.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.evaluation_metrics import evaluate_three_way


@dataclass
class Aggregate:
    n: int = 0
    brier: float = 0.0
    log_loss: float = 0.0
    rps: float = 0.0
    correct: int = 0

    def add(self, *, brier: float, log_loss: float, rps: float, correct: bool) -> None:
        self.n += 1
        self.brier += brier
        self.log_loss += log_loss
        self.rps += rps
        self.correct += int(correct)

    def row(self, label: str) -> str:
        if self.n == 0:
            return f"{label:42} n=0"
        return (
            f"{label:42} n={self.n:4d} "
            f"log_loss={self.log_loss / self.n:.4f} "
            f"brier={self.brier / self.n:.4f} "
            f"rps={self.rps / self.n:.4f} "
            f"acc={self.correct / self.n:.3f}"
        )


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00").replace(" ", "T")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(text.split(".")[0])
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _horizon(as_of_time: datetime, kickoff: datetime) -> str:
    hours = (kickoff - as_of_time).total_seconds() / 3600
    if 18 <= hours <= 30:
        return "t_minus_24h"
    if 3 <= hours < 9:
        return "t_minus_6h"
    if 0 <= hours < 3:
        return "t_minus_90m"
    if hours >= 0:
        return "other_prematch"
    return "after_kickoff"


def _load_prediction_run_rows(conn: sqlite3.Connection, limit: int | None) -> list[sqlite3.Row]:
    query = """
        SELECT
            'prediction_runs' AS source,
            pr.id,
            pr.match_id,
            pr.run_type,
            pr.model_version,
            pr.as_of_time,
            pr.home_win_prob,
            pr.draw_prob,
            pr.away_win_prob,
            m.match_date,
            m.competition,
            COALESCE(m.stage, '') AS stage,
            COALESCE(m.is_neutral_venue, 0) AS is_neutral_venue,
            mr.home_goals,
            mr.away_goals
        FROM prediction_runs pr
        JOIN matches m
          ON REPLACE(CAST(pr.match_id AS TEXT), '-', '') = REPLACE(CAST(m.id AS TEXT), '-', '')
        JOIN match_results mr
          ON REPLACE(CAST(mr.match_id AS TEXT), '-', '') = REPLACE(CAST(m.id AS TEXT), '-', '')
        WHERE mr.home_goals IS NOT NULL
          AND mr.away_goals IS NOT NULL
        ORDER BY pr.as_of_time ASC
    """
    if limit:
        query += " LIMIT ?"
        return list(conn.execute(query, (limit,)))
    return list(conn.execute(query))


def _load_snapshot_rows(conn: sqlite3.Connection, limit: int | None) -> list[sqlite3.Row]:
    query = """
        SELECT
            'prediction_snapshots' AS source,
            ps.id,
            ps.match_id,
            ps.run_type,
            ps.model_version,
            ps.generated_at AS as_of_time,
            ps.baseline_probs,
            ps.adjusted_probs,
            ps.component_probs,
            ps.market_probs,
            m.match_date,
            m.competition,
            COALESCE(m.stage, '') AS stage,
            COALESCE(m.is_neutral_venue, 0) AS is_neutral_venue,
            mr.home_goals,
            mr.away_goals
        FROM prediction_snapshots ps
        JOIN matches m
          ON REPLACE(CAST(ps.match_id AS TEXT), '-', '') = REPLACE(CAST(m.id AS TEXT), '-', '')
        JOIN match_results mr
          ON REPLACE(CAST(mr.match_id AS TEXT), '-', '') = REPLACE(CAST(m.id AS TEXT), '-', '')
        WHERE mr.home_goals IS NOT NULL
          AND mr.away_goals IS NOT NULL
          AND ps.match_id IS NOT NULL
          AND TRIM(ps.match_id) <> ''
        ORDER BY ps.generated_at ASC
    """
    if limit:
        query += " LIMIT ?"
        return list(conn.execute(query, (limit,)))
    return list(conn.execute(query))


def _json_obj(raw: object) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(str(raw))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _prob_tuple(data: dict) -> tuple[float, float, float] | None:
    home = data.get("home", data.get("home_win_prob"))
    draw = data.get("draw", data.get("draw_prob"))
    away = data.get("away", data.get("away_win_prob"))
    if home is None or draw is None or away is None:
        return None
    return (float(home), float(draw), float(away))


def _component_label(name: str) -> str:
    normalized = name.lower()
    return {
        "dc": "dc_only",
        "dixon_coles": "dc_only",
        "enhancer": "tabular_only",
        "tabular": "tabular_only",
        "elo": "elo_only",
        "pi": "pi_only",
        "pi_rating": "pi_only",
        "weibull": "weibull_only",
        "market": "market_only",
    }.get(normalized, f"component:{normalized}")


def _add_metrics(
    aggregates: dict[str, Aggregate],
    *,
    label: str,
    home_prob: float,
    draw_prob: float,
    away_prob: float,
    home_goals: int,
    away_goals: int,
) -> None:
    metrics = evaluate_three_way(
        home_prob=home_prob,
        draw_prob=draw_prob,
        away_prob=away_prob,
        home_goals=home_goals,
        away_goals=away_goals,
    )
    aggregates[label].add(
        brier=metrics.brier,
        log_loss=metrics.log_loss,
        rps=metrics.rps,
        correct=metrics.correct,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate stored predictions with walk-forward gates.")
    parser.add_argument("--db", default=str(PROJECT_ROOT / "data" / "local_stage2.db"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--min-sample", type=int, default=20)
    args = parser.parse_args(argv)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    run_rows = _load_prediction_run_rows(conn, args.limit)
    snapshot_rows = _load_snapshot_rows(conn, args.limit)

    by_baseline: dict[str, Aggregate] = defaultdict(Aggregate)
    by_model: dict[str, Aggregate] = defaultdict(Aggregate)
    by_run_type: dict[str, Aggregate] = defaultdict(Aggregate)
    by_competition: dict[str, Aggregate] = defaultdict(Aggregate)
    by_horizon: dict[str, Aggregate] = defaultdict(Aggregate)
    skipped_after_kickoff = 0
    skipped_bad_time = 0

    def _record_context(row: sqlite3.Row, metrics_label: str, metrics: Aggregate, horizon: str) -> None:
        by_model[f"{row['model_version']}::{metrics_label}"].n += metrics.n
        by_model[f"{row['model_version']}::{metrics_label}"].brier += metrics.brier
        by_model[f"{row['model_version']}::{metrics_label}"].log_loss += metrics.log_loss
        by_model[f"{row['model_version']}::{metrics_label}"].rps += metrics.rps
        by_model[f"{row['model_version']}::{metrics_label}"].correct += metrics.correct
        by_run_type[f"{row['run_type']}::{metrics_label}"].n += metrics.n
        by_run_type[f"{row['run_type']}::{metrics_label}"].brier += metrics.brier
        by_run_type[f"{row['run_type']}::{metrics_label}"].log_loss += metrics.log_loss
        by_run_type[f"{row['run_type']}::{metrics_label}"].rps += metrics.rps
        by_run_type[f"{row['run_type']}::{metrics_label}"].correct += metrics.correct
        by_competition[f"{row['competition']}::{metrics_label}"].n += metrics.n
        by_competition[f"{row['competition']}::{metrics_label}"].brier += metrics.brier
        by_competition[f"{row['competition']}::{metrics_label}"].log_loss += metrics.log_loss
        by_competition[f"{row['competition']}::{metrics_label}"].rps += metrics.rps
        by_competition[f"{row['competition']}::{metrics_label}"].correct += metrics.correct
        by_horizon[f"{horizon}::{metrics_label}"].n += metrics.n
        by_horizon[f"{horizon}::{metrics_label}"].brier += metrics.brier
        by_horizon[f"{horizon}::{metrics_label}"].log_loss += metrics.log_loss
        by_horizon[f"{horizon}::{metrics_label}"].rps += metrics.rps
        by_horizon[f"{horizon}::{metrics_label}"].correct += metrics.correct

    for row in run_rows:
        as_of_time = _parse_time(row["as_of_time"])
        kickoff = _parse_time(row["match_date"])
        if as_of_time is None or kickoff is None:
            skipped_bad_time += 1
            continue
        if as_of_time > kickoff:
            skipped_after_kickoff += 1
            continue
        horizon = _horizon(as_of_time, kickoff)

        metrics = evaluate_three_way(
            home_prob=row["home_win_prob"],
            draw_prob=row["draw_prob"],
            away_prob=row["away_win_prob"],
            home_goals=row["home_goals"],
            away_goals=row["away_goals"],
        )
        agg = Aggregate()
        agg.add(brier=metrics.brier, log_loss=metrics.log_loss, rps=metrics.rps, correct=metrics.correct)
        by_baseline["current_fusion"].add(
            brier=metrics.brier, log_loss=metrics.log_loss, rps=metrics.rps, correct=metrics.correct
        )
        _record_context(row, "current_fusion", agg, horizon)
        _add_metrics(
            by_baseline,
            label="uniform_baseline",
            home_prob=1 / 3,
            draw_prob=1 / 3,
            away_prob=1 / 3,
            home_goals=row["home_goals"],
            away_goals=row["away_goals"],
        )

    for row in snapshot_rows:
        as_of_time = _parse_time(row["as_of_time"])
        kickoff = _parse_time(row["match_date"])
        if as_of_time is None or kickoff is None:
            skipped_bad_time += 1
            continue
        if as_of_time > kickoff:
            skipped_after_kickoff += 1
            continue
        horizon = _horizon(as_of_time, kickoff)

        candidates: list[tuple[str, tuple[float, float, float]]] = []
        for label, raw in [
            ("snapshot_baseline", row["baseline_probs"]),
            ("snapshot_adjusted", row["adjusted_probs"]),
            ("market_only", row["market_probs"]),
        ]:
            probs = _prob_tuple(_json_obj(raw))
            if probs:
                candidates.append((label, probs))

        for name, probs_obj in _json_obj(row["component_probs"]).items():
            if isinstance(probs_obj, dict):
                probs = _prob_tuple(probs_obj)
                if probs:
                    candidates.append((_component_label(name), probs))

        for label, probs in candidates:
            metrics = evaluate_three_way(
                home_prob=probs[0],
                draw_prob=probs[1],
                away_prob=probs[2],
                home_goals=row["home_goals"],
                away_goals=row["away_goals"],
            )
            agg = Aggregate()
            agg.add(brier=metrics.brier, log_loss=metrics.log_loss, rps=metrics.rps, correct=metrics.correct)
            by_baseline[label].add(
                brier=metrics.brier,
                log_loss=metrics.log_loss,
                rps=metrics.rps,
                correct=metrics.correct,
            )
            _record_context(row, label, agg, horizon)

    print("=" * 78)
    print("WALK-FORWARD EVALUATION: stored prediction_runs + prediction_snapshots")
    print("=" * 78)
    print(f"DB: {args.db}")
    print(f"PredictionRun rows loaded: {len(run_rows)}")
    print(f"PredictionSnapshot rows loaded: {len(snapshot_rows)}")
    print(f"Current fusion rows evaluated: {by_baseline['current_fusion'].n}")
    print(f"Skipped after kickoff: {skipped_after_kickoff}")
    print(f"Skipped bad timestamps: {skipped_bad_time}")

    print("\n--- model / baseline leaderboard ---")
    for label, agg in sorted(by_baseline.items(), key=lambda item: (item[1].log_loss / item[1].n if item[1].n else 999, item[0])):
        if agg.n >= args.min_sample:
            print(agg.row(label))

    print("\n--- by model_version ---")
    for label, agg in sorted(by_model.items(), key=lambda item: (-item[1].n, item[0])):
        if agg.n >= args.min_sample:
            print(agg.row(label))

    print("\n--- by run_type ---")
    for label, agg in sorted(by_run_type.items(), key=lambda item: (-item[1].n, item[0])):
        if agg.n >= args.min_sample:
            print(agg.row(label))

    print("\n--- by competition ---")
    for label, agg in sorted(by_competition.items(), key=lambda item: (-item[1].n, item[0])):
        if agg.n >= args.min_sample:
            print(agg.row(label[:42]))

    print("\n--- by horizon ---")
    for label, agg in sorted(by_horizon.items(), key=lambda item: (-item[1].n, item[0])):
        if agg.n >= args.min_sample:
            print(agg.row(label[:42]))

    if by_baseline["current_fusion"].n < args.min_sample:
        print(f"\nFAIL: only {by_baseline['current_fusion'].n} current_fusion rows; need at least {args.min_sample}.")
        return 2
    print("\nOK: walk-forward report generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

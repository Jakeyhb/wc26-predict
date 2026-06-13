#!/usr/bin/env python3
"""Walk-forward champion/challenger evaluation over stored predictions.

The script evaluates only predictions whose as_of_time/generated_at is not
after kickoff. It emits a structured report and a release-gate decision without
retraining models.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.evaluation_metrics import ThreeWayMetrics, evaluate_three_way
from app.services.evaluation_sample import normalize_1x2_payload


PROPER_METRICS = ("log_loss", "brier", "rps")


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

    def add_metrics(self, metrics: ThreeWayMetrics) -> None:
        self.add(brier=metrics.brier, log_loss=metrics.log_loss, rps=metrics.rps, correct=metrics.correct)

    def merge(self, other: "Aggregate") -> None:
        self.n += other.n
        self.brier += other.brier
        self.log_loss += other.log_loss
        self.rps += other.rps
        self.correct += other.correct

    def averages(self) -> dict[str, float | int]:
        if self.n == 0:
            return {"n": 0, "log_loss": 0.0, "brier": 0.0, "rps": 0.0, "accuracy": 0.0}
        return {
            "n": self.n,
            "log_loss": self.log_loss / self.n,
            "brier": self.brier / self.n,
            "rps": self.rps / self.n,
            "accuracy": self.correct / self.n,
        }

    def row(self, label: str) -> str:
        if self.n == 0:
            return f"{label:42} n=0"
        avg = self.averages()
        return (
            f"{label:42} n={self.n:4d} "
            f"log_loss={avg['log_loss']:.4f} "
            f"brier={avg['brier']:.4f} "
            f"rps={avg['rps']:.4f} "
            f"acc={avg['accuracy']:.3f}"
        )


@dataclass(frozen=True)
class GateConfig:
    champion_label: str
    min_sample: int
    group_min_sample: int
    max_group_regression: float


@dataclass
class EvaluationExample:
    example_id: str
    source: str
    prediction_id: str
    match_id: str
    as_of_time: str
    horizon: str
    competition: str
    run_type: str
    model_version: str
    schema_version: str
    scores: dict[str, ThreeWayMetrics]


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
            pr.input_feature_snapshot,
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
            ps.pipeline_params,
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


def _split_group_label(label: str) -> tuple[str, str]:
    if "::" not in label:
        return label, ""
    return label.rsplit("::", 1)


def _summary_map(aggregates: dict[str, Aggregate], min_sample: int = 0) -> dict[str, dict[str, float | int]]:
    return {
        label: agg.averages()
        for label, agg in sorted(aggregates.items())
        if agg.n >= min_sample
    }


def _better_metric_count(candidate: dict[str, Any], baseline: dict[str, Any]) -> int:
    return sum(float(candidate[metric]) < float(baseline[metric]) for metric in PROPER_METRICS)


def _metric_delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    return {metric: float(candidate[metric]) - float(baseline[metric]) for metric in PROPER_METRICS}


def _find_group_regressions(
    groups: dict[str, Aggregate],
    *,
    group_name: str,
    champion_label: str,
    baseline_label: str,
    group_min_sample: int,
    max_group_regression: float,
) -> list[dict[str, Any]]:
    by_group: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for label, agg in groups.items():
        group_value, metric_label = _split_group_label(label)
        if agg.n >= group_min_sample:
            by_group[group_value][metric_label] = agg.averages()

    regressions: list[dict[str, Any]] = []
    for group_value, labels in sorted(by_group.items()):
        champion = labels.get(champion_label)
        baseline = labels.get(baseline_label)
        if not champion or not baseline:
            continue
        deltas = _metric_delta(champion, baseline)
        bad_metrics = {
            metric: delta
            for metric, delta in deltas.items()
            if metric in {"log_loss", "brier"} and delta > max_group_regression
        }
        if bad_metrics:
            regressions.append(
                {
                    "group_type": group_name,
                    "group": group_value,
                    "champion": champion,
                    "baseline": baseline,
                    "deltas": deltas,
                    "bad_metrics": bad_metrics,
                }
            )
    return regressions


def _parse_label_list(raw: str | list[str] | tuple[str, ...]) -> list[str]:
    if isinstance(raw, str):
        labels = raw.split(",")
    else:
        labels = list(raw)
    return [label.strip() for label in labels if label and label.strip()]


def _example_group_value(example: EvaluationExample, group_name: str) -> str:
    if group_name == "horizon":
        return example.horizon
    if group_name == "competition":
        return example.competition
    if group_name == "run_type":
        return example.run_type
    raise ValueError(f"unsupported paired group: {group_name}")


def _aggregate_metrics(metrics: list[ThreeWayMetrics]) -> Aggregate:
    aggregate = Aggregate()
    for item in metrics:
        aggregate.add_metrics(item)
    return aggregate


def _paired_examples_for_labels(
    examples: list[EvaluationExample],
    candidate_label: str,
    baseline_label: str,
) -> list[EvaluationExample]:
    return [
        example
        for example in examples
        if candidate_label in example.scores and baseline_label in example.scores
    ]


def _cohort_counts(examples: list[EvaluationExample]) -> dict[str, Any]:
    by_source: dict[str, int] = defaultdict(int)
    by_schema_version: dict[str, int] = defaultdict(int)
    by_label: dict[str, int] = defaultdict(int)
    by_source_label: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for example in examples:
        by_source[example.source] += 1
        by_schema_version[example.schema_version] += 1
        for label in example.scores:
            by_label[label] += 1
            by_source_label[example.source][label] += 1
    return {
        "total_examples": len(examples),
        "by_source": dict(sorted(by_source.items())),
        "by_schema_version": dict(sorted(by_schema_version.items())),
        "by_label": dict(sorted(by_label.items())),
        "by_source_label": {
            source: dict(sorted(labels.items()))
            for source, labels in sorted(by_source_label.items())
        },
    }


def _paired_comparison(
    examples: list[EvaluationExample],
    *,
    candidate_label: str,
    baseline_label: str,
    min_sample: int,
) -> dict[str, Any]:
    paired_examples = _paired_examples_for_labels(examples, candidate_label, baseline_label)
    by_source: dict[str, int] = defaultdict(int)
    for example in paired_examples:
        by_source[example.source] += 1

    if len(paired_examples) < min_sample:
        return {
            "status": "insufficient_samples",
            "candidate_label": candidate_label,
            "baseline_label": baseline_label,
            "available_n": len(paired_examples),
            "min_sample": min_sample,
            "by_source": dict(sorted(by_source.items())),
        }

    candidate = _aggregate_metrics([example.scores[candidate_label] for example in paired_examples]).averages()
    baseline = _aggregate_metrics([example.scores[baseline_label] for example in paired_examples]).averages()
    return {
        "status": "evaluated",
        "candidate_label": candidate_label,
        "baseline_label": baseline_label,
        "n": len(paired_examples),
        "candidate": candidate,
        "baseline": baseline,
        "deltas": _metric_delta(candidate, baseline),
        "better_metric_count": _better_metric_count(candidate, baseline),
        "by_source": dict(sorted(by_source.items())),
    }


def _find_paired_group_regressions(
    examples: list[EvaluationExample],
    *,
    group_name: str,
    candidate_label: str,
    baseline_label: str,
    group_min_sample: int,
    max_group_regression: float,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[EvaluationExample]] = defaultdict(list)
    for example in _paired_examples_for_labels(examples, candidate_label, baseline_label):
        grouped[_example_group_value(example, group_name)].append(example)

    regressions: list[dict[str, Any]] = []
    for group_value, paired_examples in sorted(grouped.items()):
        if len(paired_examples) < group_min_sample:
            continue
        candidate = _aggregate_metrics([example.scores[candidate_label] for example in paired_examples]).averages()
        baseline = _aggregate_metrics([example.scores[baseline_label] for example in paired_examples]).averages()
        deltas = _metric_delta(candidate, baseline)
        bad_metrics = {
            metric: delta
            for metric, delta in deltas.items()
            if metric in {"log_loss", "brier"} and delta > max_group_regression
        }
        if bad_metrics:
            regressions.append(
                {
                    "group_type": group_name,
                    "group": group_value,
                    "n": len(paired_examples),
                    "candidate": candidate,
                    "baseline": baseline,
                    "deltas": deltas,
                    "bad_metrics": bad_metrics,
                }
            )
    return regressions


def build_paired_report(
    examples: list[EvaluationExample],
    *,
    paired_champion_label: str,
    paired_baselines: list[str],
    min_sample: int,
    group_min_sample: int,
    max_group_regression: float,
) -> dict[str, Any]:
    comparisons: dict[str, Any] = {}
    insufficient: dict[str, Any] = {}
    for baseline_label in paired_baselines:
        if baseline_label == paired_champion_label:
            continue
        comparison = _paired_comparison(
            examples,
            candidate_label=paired_champion_label,
            baseline_label=baseline_label,
            min_sample=min_sample,
        )
        comparisons[baseline_label] = comparison
        if comparison["status"] == "insufficient_samples":
            insufficient[baseline_label] = comparison

    reasons: list[str] = []
    warnings: list[str] = []
    uniform = comparisons.get("uniform_baseline")
    if uniform is None:
        reasons.append("uniform_baseline is missing from paired baselines")
    elif uniform["status"] == "insufficient_samples":
        reasons.append("uniform_baseline has insufficient paired samples for required gate comparison")
    else:
        champion = uniform["candidate"]
        baseline = uniform["baseline"]
        if float(champion["log_loss"]) >= float(baseline["log_loss"]):
            reasons.append("paired champion log_loss is not better than uniform_baseline")
        if float(champion["brier"]) >= float(baseline["brier"]):
            reasons.append("paired champion brier is not better than uniform_baseline")
        if int(uniform["better_metric_count"]) < 2:
            reasons.append("paired champion does not beat uniform_baseline on at least two proper scoring metrics")

    for baseline_label, item in insufficient.items():
        if baseline_label != "uniform_baseline":
            warnings.append(
                f"{baseline_label} has only {item['available_n']} paired samples; "
                f"need {item['min_sample']}"
            )

    group_regressions: list[dict[str, Any]] = []
    if uniform is not None and uniform["status"] == "evaluated":
        for group_name in ["horizon", "competition", "run_type"]:
            group_regressions.extend(
                _find_paired_group_regressions(
                    examples,
                    group_name=group_name,
                    candidate_label=paired_champion_label,
                    baseline_label="uniform_baseline",
                    group_min_sample=group_min_sample,
                    max_group_regression=max_group_regression,
                )
            )
    if group_regressions:
        reasons.append(f"paired champion has {len(group_regressions)} critical group regression(s) vs uniform_baseline")

    return {
        "cohorts": _cohort_counts(examples),
        "comparisons": comparisons,
        "insufficient_baselines": insufficient,
        "gate": {
            "status": "pass" if not reasons else "fail",
            "champion_label": paired_champion_label,
            "baseline_labels": paired_baselines,
            "min_sample": min_sample,
            "group_min_sample": group_min_sample,
            "max_group_regression": max_group_regression,
            "required_baseline": "uniform_baseline",
            "group_regressions": group_regressions,
            "reasons": reasons,
            "warnings": warnings,
        },
    }


def decide_champion_gate(
    *,
    leaderboard: dict[str, Aggregate],
    by_horizon: dict[str, Aggregate],
    by_competition: dict[str, Aggregate],
    by_run_type: dict[str, Aggregate],
    config: GateConfig,
) -> dict[str, Any]:
    eligible = _summary_map(leaderboard, config.min_sample)
    reasons: list[str] = []
    warnings: list[str] = []
    comparisons: dict[str, Any] = {}

    champion = eligible.get(config.champion_label)
    if champion is None:
        reasons.append(f"champion '{config.champion_label}' has fewer than {config.min_sample} samples")

    leader_label = None
    if eligible:
        leader_label = min(
            eligible,
            key=lambda label: (
                float(eligible[label]["log_loss"]),
                float(eligible[label]["brier"]),
                float(eligible[label]["rps"]),
                label,
            ),
        )
        if champion is not None and leader_label != config.champion_label:
            reasons.append(f"champion is not leaderboard leader by log_loss: leader={leader_label}")

    if champion is not None:
        uniform = eligible.get("uniform_baseline")
        if uniform is None:
            reasons.append("uniform_baseline has insufficient samples for required gate comparison")
        else:
            comparisons["uniform_baseline"] = {
                "baseline": uniform,
                "deltas": _metric_delta(champion, uniform),
                "better_metric_count": _better_metric_count(champion, uniform),
            }
            if float(champion["log_loss"]) >= float(uniform["log_loss"]):
                reasons.append("champion log_loss is not better than uniform_baseline")
            if float(champion["brier"]) >= float(uniform["brier"]):
                reasons.append("champion brier is not better than uniform_baseline")
            if _better_metric_count(champion, uniform) < 2:
                reasons.append("champion does not beat uniform_baseline on at least two proper scoring metrics")

        for baseline_label in ["dc_only", "elo_only", "pi_only", "weibull_only", "tabular_only", "market_only"]:
            baseline = eligible.get(baseline_label)
            if baseline is None:
                warnings.append(f"{baseline_label} has fewer than {config.min_sample} samples")
                continue
            comparisons[baseline_label] = {
                "baseline": baseline,
                "deltas": _metric_delta(champion, baseline),
                "better_metric_count": _better_metric_count(champion, baseline),
                "paired": False,
                "note": "unpaired benchmark; sample sets may differ",
            }

    group_regressions: list[dict[str, Any]] = []
    for group_name, groups in [
        ("horizon", by_horizon),
        ("competition", by_competition),
        ("run_type", by_run_type),
    ]:
        group_regressions.extend(
            _find_group_regressions(
                groups,
                group_name=group_name,
                champion_label=config.champion_label,
                baseline_label="uniform_baseline",
                group_min_sample=config.group_min_sample,
                max_group_regression=config.max_group_regression,
            )
        )
    if group_regressions:
        reasons.append(f"champion has {len(group_regressions)} critical group regression(s) vs uniform_baseline")

    return {
        "status": "pass" if not reasons else "fail",
        "champion_label": config.champion_label,
        "leader_label": leader_label,
        "min_sample": config.min_sample,
        "group_min_sample": config.group_min_sample,
        "max_group_regression": config.max_group_regression,
        "champion": champion,
        "eligible_labels": sorted(eligible),
        "comparisons": comparisons,
        "group_regressions": group_regressions,
        "reasons": reasons,
        "warnings": warnings,
    }


def _record_context(
    *,
    row: sqlite3.Row,
    metrics_label: str,
    metrics: ThreeWayMetrics,
    horizon: str,
    by_model: dict[str, Aggregate],
    by_run_type: dict[str, Aggregate],
    by_competition: dict[str, Aggregate],
    by_horizon: dict[str, Aggregate],
) -> None:
    agg = Aggregate()
    agg.add_metrics(metrics)
    by_model[f"{row['model_version']}::{metrics_label}"].merge(agg)
    by_run_type[f"{row['run_type']}::{metrics_label}"].merge(agg)
    by_competition[f"{row['competition']}::{metrics_label}"].merge(agg)
    by_horizon[f"{horizon}::{metrics_label}"].merge(agg)


def _add_prediction_metrics(
    aggregates: dict[str, Aggregate],
    *,
    label: str,
    home_prob: float,
    draw_prob: float,
    away_prob: float,
    home_goals: int,
    away_goals: int,
) -> ThreeWayMetrics:
    metrics = evaluate_three_way(
        home_prob=home_prob,
        draw_prob=draw_prob,
        away_prob=away_prob,
        home_goals=home_goals,
        away_goals=away_goals,
    )
    aggregates[label].add_metrics(metrics)
    return metrics


def _make_example(row: sqlite3.Row, *, horizon: str, schema_version: str = "legacy_fallback") -> EvaluationExample:
    return EvaluationExample(
        example_id=f"{row['source']}:{row['id']}",
        source=str(row["source"]),
        prediction_id=str(row["id"]),
        match_id=str(row["match_id"]),
        as_of_time=str(row["as_of_time"]),
        horizon=horizon,
        competition=str(row["competition"]),
        run_type=str(row["run_type"]),
        model_version=str(row["model_version"]),
        schema_version=schema_version,
        scores={},
    )


def _add_example_score(
    example: EvaluationExample,
    *,
    label: str,
    home_prob: float,
    draw_prob: float,
    away_prob: float,
    home_goals: int,
    away_goals: int,
) -> ThreeWayMetrics:
    metrics = evaluate_three_way(
        home_prob=home_prob,
        draw_prob=draw_prob,
        away_prob=away_prob,
        home_goals=home_goals,
        away_goals=away_goals,
    )
    example.scores[label] = metrics
    return metrics


def _evaluation_candidates_from_container(raw: object) -> tuple[str, dict[str, dict[str, float]]] | None:
    container = _json_obj(raw)
    sample = container.get("evaluation_sample")
    if not isinstance(sample, dict):
        return None
    raw_candidates = sample.get("candidate_probs")
    if not isinstance(raw_candidates, dict):
        return None
    candidates: dict[str, dict[str, float]] = {}
    for label, payload in raw_candidates.items():
        probs = normalize_1x2_payload(payload)
        if probs:
            candidates[str(label)] = probs
    if not candidates:
        return None
    return str(sample.get("schema_version") or "unknown"), candidates


def _record_candidate(
    *,
    row: sqlite3.Row,
    example: EvaluationExample,
    label: str,
    probs: dict[str, float] | tuple[float, float, float],
    home_goals: int,
    away_goals: int,
    horizon: str,
    by_baseline: dict[str, Aggregate],
    by_model: dict[str, Aggregate],
    by_run_type: dict[str, Aggregate],
    by_competition: dict[str, Aggregate],
    by_horizon: dict[str, Aggregate],
) -> None:
    if isinstance(probs, tuple):
        home_prob, draw_prob, away_prob = probs
    else:
        home_prob = probs["home"]
        draw_prob = probs["draw"]
        away_prob = probs["away"]
    metrics = _add_prediction_metrics(
        by_baseline,
        label=label,
        home_prob=home_prob,
        draw_prob=draw_prob,
        away_prob=away_prob,
        home_goals=home_goals,
        away_goals=away_goals,
    )
    _record_context(
        row=row,
        metrics_label=label,
        metrics=metrics,
        horizon=horizon,
        by_model=by_model,
        by_run_type=by_run_type,
        by_competition=by_competition,
        by_horizon=by_horizon,
    )
    example.scores[label] = metrics


def build_walk_forward_report(
    *,
    conn: sqlite3.Connection,
    db_path: str,
    limit: int | None,
    min_sample: int,
    group_min_sample: int,
    max_group_regression: float,
    champion_label: str,
    paired_champion_label: str,
    paired_baselines: list[str],
) -> dict[str, Any]:
    run_rows = _load_prediction_run_rows(conn, limit)
    snapshot_rows = _load_snapshot_rows(conn, limit)

    by_baseline: dict[str, Aggregate] = defaultdict(Aggregate)
    by_model: dict[str, Aggregate] = defaultdict(Aggregate)
    by_run_type: dict[str, Aggregate] = defaultdict(Aggregate)
    by_competition: dict[str, Aggregate] = defaultdict(Aggregate)
    by_horizon: dict[str, Aggregate] = defaultdict(Aggregate)
    paired_examples: list[EvaluationExample] = []
    pipeline_evaluation_examples = 0
    skipped_after_kickoff = 0
    skipped_bad_time = 0

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
        sample_candidates = _evaluation_candidates_from_container(row["input_feature_snapshot"])
        if sample_candidates:
            schema_version, candidates = sample_candidates
            example = _make_example(row, horizon=horizon, schema_version=schema_version)
            for label, probs in candidates.items():
                _record_candidate(
                    row=row,
                    example=example,
                    label=label,
                    probs=probs,
                    home_goals=row["home_goals"],
                    away_goals=row["away_goals"],
                    horizon=horizon,
                    by_baseline=by_baseline,
                    by_model=by_model,
                    by_run_type=by_run_type,
                    by_competition=by_competition,
                    by_horizon=by_horizon,
                )
            paired_examples.append(example)
            pipeline_evaluation_examples += 1
            continue

        example = _make_example(row, horizon=horizon)

        current_metrics = _add_prediction_metrics(
            by_baseline,
            label="current_fusion",
            home_prob=row["home_win_prob"],
            draw_prob=row["draw_prob"],
            away_prob=row["away_win_prob"],
            home_goals=row["home_goals"],
            away_goals=row["away_goals"],
        )
        _record_context(
            row=row,
            metrics_label="current_fusion",
            metrics=current_metrics,
            horizon=horizon,
            by_model=by_model,
            by_run_type=by_run_type,
            by_competition=by_competition,
            by_horizon=by_horizon,
        )
        example.scores["current_fusion"] = current_metrics

        uniform_metrics = _add_prediction_metrics(
            by_baseline,
            label="uniform_baseline",
            home_prob=1 / 3,
            draw_prob=1 / 3,
            away_prob=1 / 3,
            home_goals=row["home_goals"],
            away_goals=row["away_goals"],
        )
        _record_context(
            row=row,
            metrics_label="uniform_baseline",
            metrics=uniform_metrics,
            horizon=horizon,
            by_model=by_model,
            by_run_type=by_run_type,
            by_competition=by_competition,
            by_horizon=by_horizon,
        )
        example.scores["uniform_baseline"] = uniform_metrics
        paired_examples.append(example)

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
        sample_candidates = _evaluation_candidates_from_container(row["pipeline_params"])
        if sample_candidates:
            schema_version, candidates = sample_candidates
            example = _make_example(row, horizon=horizon, schema_version=schema_version)
            for label, probs in candidates.items():
                _record_candidate(
                    row=row,
                    example=example,
                    label=label,
                    probs=probs,
                    home_goals=row["home_goals"],
                    away_goals=row["away_goals"],
                    horizon=horizon,
                    by_baseline=by_baseline,
                    by_model=by_model,
                    by_run_type=by_run_type,
                    by_competition=by_competition,
                    by_horizon=by_horizon,
                )
            paired_examples.append(example)
            pipeline_evaluation_examples += 1
            continue

        example = _make_example(row, horizon=horizon)
        _add_example_score(
            example,
            label="uniform_baseline",
            home_prob=1 / 3,
            draw_prob=1 / 3,
            away_prob=1 / 3,
            home_goals=row["home_goals"],
            away_goals=row["away_goals"],
        )

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
            metrics = _add_prediction_metrics(
                by_baseline,
                label=label,
                home_prob=probs[0],
                draw_prob=probs[1],
                away_prob=probs[2],
                home_goals=row["home_goals"],
                away_goals=row["away_goals"],
            )
            _record_context(
                row=row,
                metrics_label=label,
                metrics=metrics,
                horizon=horizon,
                by_model=by_model,
                by_run_type=by_run_type,
                by_competition=by_competition,
                by_horizon=by_horizon,
            )
            example.scores[label] = metrics
        paired_examples.append(example)

    gate = decide_champion_gate(
        leaderboard=by_baseline,
        by_horizon=by_horizon,
        by_competition=by_competition,
        by_run_type=by_run_type,
        config=GateConfig(
            champion_label=champion_label,
            min_sample=min_sample,
            group_min_sample=group_min_sample,
            max_group_regression=max_group_regression,
        ),
    )
    paired = build_paired_report(
        paired_examples,
        paired_champion_label=paired_champion_label,
        paired_baselines=paired_baselines,
        min_sample=min_sample,
        group_min_sample=group_min_sample,
        max_group_regression=max_group_regression,
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": db_path,
        "min_sample": min_sample,
        "group_min_sample": group_min_sample,
        "max_group_regression": max_group_regression,
        "loaded": {
            "prediction_runs": len(run_rows),
            "prediction_snapshots": len(snapshot_rows),
            "current_fusion_evaluated": by_baseline["current_fusion"].n,
            "paired_examples": len(paired_examples),
            "pipeline_evaluation_examples": pipeline_evaluation_examples,
            "skipped_after_kickoff": skipped_after_kickoff,
            "skipped_bad_timestamps": skipped_bad_time,
        },
        "leaderboard": _summary_map(by_baseline),
        "groups": {
            "model_version": _summary_map(by_model),
            "run_type": _summary_map(by_run_type),
            "competition": _summary_map(by_competition),
            "horizon": _summary_map(by_horizon),
        },
        "gate": gate,
        "paired": paired,
    }


def _sorted_items(summary: dict[str, dict[str, Any]], min_sample: int) -> list[tuple[str, dict[str, Any]]]:
    return sorted(
        ((label, row) for label, row in summary.items() if int(row["n"]) >= min_sample),
        key=lambda item: (float(item[1]["log_loss"]), float(item[1]["brier"]), item[0]),
    )


def _print_summary(report: dict[str, Any], *, min_sample: int) -> None:
    print("=" * 78)
    print("WALK-FORWARD CHAMPION GATE: stored prediction_runs + prediction_snapshots")
    print("=" * 78)
    print(f"DB: {report['db_path']}")
    print(f"PredictionRun rows loaded: {report['loaded']['prediction_runs']}")
    print(f"PredictionSnapshot rows loaded: {report['loaded']['prediction_snapshots']}")
    print(f"Current fusion rows evaluated: {report['loaded']['current_fusion_evaluated']}")
    print(f"Paired evaluation examples: {report['loaded']['paired_examples']}")
    print(f"Pipeline evaluation examples: {report['loaded']['pipeline_evaluation_examples']}")
    print(f"Skipped after kickoff: {report['loaded']['skipped_after_kickoff']}")
    print(f"Skipped bad timestamps: {report['loaded']['skipped_bad_timestamps']}")

    print("\n--- exploratory unpaired model / baseline leaderboard ---")
    for label, row in _sorted_items(report["leaderboard"], min_sample):
        print(
            f"{label:42} n={int(row['n']):4d} "
            f"log_loss={float(row['log_loss']):.4f} "
            f"brier={float(row['brier']):.4f} "
            f"rps={float(row['rps']):.4f} "
            f"acc={float(row['accuracy']):.3f}"
        )

    for group_name, title in [
        ("model_version", "by model_version"),
        ("run_type", "by run_type"),
        ("competition", "by competition"),
        ("horizon", "by horizon"),
    ]:
        print(f"\n--- {title} ---")
        items = sorted(
            ((label, row) for label, row in report["groups"][group_name].items() if int(row["n"]) >= min_sample),
            key=lambda item: (-int(item[1]["n"]), item[0]),
        )
        for label, row in items:
            print(
                f"{label[:42]:42} n={int(row['n']):4d} "
                f"log_loss={float(row['log_loss']):.4f} "
                f"brier={float(row['brier']):.4f} "
                f"rps={float(row['rps']):.4f} "
                f"acc={float(row['accuracy']):.3f}"
            )

    gate = report["gate"]
    print("\n--- champion gate ---")
    print(f"status: {gate['status'].upper()}")
    print(f"champion: {gate['champion_label']}")
    print(f"leader: {gate['leader_label']}")
    if gate["reasons"]:
        print("reasons:")
        for reason in gate["reasons"]:
            print(f"  - {reason}")
    if gate["warnings"]:
        print("warnings:")
        for warning in gate["warnings"]:
            print(f"  - {warning}")

    paired = report["paired"]
    paired_gate = paired["gate"]
    print("\n--- paired benchmark gate ---")
    print(f"status: {paired_gate['status'].upper()}")
    print(f"paired champion: {paired_gate['champion_label']}")
    print(f"paired examples: {paired['cohorts']['total_examples']}")
    print("comparisons:")
    for baseline_label, comparison in sorted(paired["comparisons"].items()):
        if comparison["status"] == "insufficient_samples":
            print(
                f"  - {baseline_label:20} insufficient_samples "
                f"available={comparison['available_n']} min={comparison['min_sample']}"
            )
            continue
        deltas = comparison["deltas"]
        print(
            f"  - {baseline_label:20} n={comparison['n']:4d} "
            f"d_log_loss={deltas['log_loss']:+.4f} "
            f"d_brier={deltas['brier']:+.4f} "
            f"d_rps={deltas['rps']:+.4f} "
            f"better={comparison['better_metric_count']}/3"
        )
    if paired_gate["reasons"]:
        print("paired gate reasons:")
        for reason in paired_gate["reasons"]:
            print(f"  - {reason}")
    if paired_gate["warnings"]:
        print("paired warnings:")
        for warning in paired_gate["warnings"]:
            print(f"  - {warning}")


def _markdown_table(rows: list[tuple[str, dict[str, Any]]]) -> str:
    lines = ["| Label | n | log loss | Brier | RPS | Accuracy |", "|---|---:|---:|---:|---:|---:|"]
    for label, row in rows:
        lines.append(
            f"| {label} | {int(row['n'])} | {float(row['log_loss']):.4f} | "
            f"{float(row['brier']):.4f} | {float(row['rps']):.4f} | {float(row['accuracy']):.3f} |"
        )
    return "\n".join(lines)


def _paired_comparison_table(comparisons: dict[str, dict[str, Any]]) -> str:
    lines = [
        "| Baseline | Status | n | Candidate log loss | Baseline log loss | Δ log loss | Candidate Brier | Baseline Brier | Δ Brier | Better metrics |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for baseline_label, item in sorted(comparisons.items()):
        if item["status"] == "insufficient_samples":
            lines.append(
                f"| {baseline_label} | insufficient_samples | {int(item['available_n'])} | "
                "|  |  |  |  |  |  |  |"
            )
            continue
        candidate = item["candidate"]
        baseline = item["baseline"]
        deltas = item["deltas"]
        lines.append(
            f"| {baseline_label} | evaluated | {int(item['n'])} | "
            f"{float(candidate['log_loss']):.4f} | {float(baseline['log_loss']):.4f} | {float(deltas['log_loss']):+.4f} | "
            f"{float(candidate['brier']):.4f} | {float(baseline['brier']):.4f} | {float(deltas['brier']):+.4f} | "
            f"{int(item['better_metric_count'])}/3 |"
        )
    return "\n".join(lines)


def _render_markdown(report: dict[str, Any], *, min_sample: int) -> str:
    gate = report["gate"]
    paired = report["paired"]
    paired_gate = paired["gate"]
    lines = [
        "# Walk-forward Champion Gate Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- DB: `{report['db_path']}`",
        f"- Unpaired gate status: **{gate['status'].upper()}**",
        f"- Paired gate status: **{paired_gate['status'].upper()}**",
        f"- Production champion candidate: `{gate['champion_label']}`",
        f"- Paired champion candidate: `{paired_gate['champion_label']}`",
        f"- Exploratory unpaired leader: `{gate['leader_label']}`",
        f"- Current fusion rows: `{report['loaded']['current_fusion_evaluated']}`",
        f"- Paired evaluation examples: `{report['loaded']['paired_examples']}`",
        f"- Pipeline evaluation examples: `{report['loaded']['pipeline_evaluation_examples']}`",
        "",
        "## Unpaired Gate Reasons",
    ]
    if gate["reasons"]:
        lines.extend(f"- {reason}" for reason in gate["reasons"])
    else:
        lines.append("- None")
    if gate["warnings"]:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in gate["warnings"])
    lines.extend(
        [
            "",
            "## Paired Gate Reasons",
        ]
    )
    if paired_gate["reasons"]:
        lines.extend(f"- {reason}" for reason in paired_gate["reasons"])
    else:
        lines.append("- None")
    if paired_gate["warnings"]:
        lines.extend(["", "## Paired Warnings"])
        lines.extend(f"- {warning}" for warning in paired_gate["warnings"])
    lines.extend(
        [
            "",
            "## Paired Comparisons",
            _paired_comparison_table(paired["comparisons"]),
            "",
            "## Exploratory Unpaired Leaderboard",
            "",
            "This leaderboard is exploratory because labels may come from different source tables and sample sets. Use the paired gate before discussing weight candidates.",
            "",
            _markdown_table(_sorted_items(report["leaderboard"], min_sample)),
        ]
    )
    if gate["group_regressions"]:
        lines.extend(["", "## Group Regressions"])
        for item in gate["group_regressions"]:
            lines.append(
                f"- `{item['group_type']}` `{item['group']}`: bad_metrics={item['bad_metrics']}"
            )
    if paired_gate["group_regressions"]:
        lines.extend(["", "## Paired Group Regressions"])
        for item in paired_gate["group_regressions"]:
            lines.append(
                f"- `{item['group_type']}` `{item['group']}` n={item['n']}: bad_metrics={item['bad_metrics']}"
            )
    return "\n".join(lines) + "\n"


def _write_reports(
    report: dict[str, Any],
    *,
    report_dir: Path,
    json_out: str | None,
    markdown_out: str | None,
    min_sample: int,
) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = Path(json_out) if json_out else report_dir / f"walk_forward_champion_gate_{stamp}.json"
    markdown_path = Path(markdown_out) if markdown_out else report_dir / f"walk_forward_champion_gate_{stamp}.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_render_markdown(report, min_sample=min_sample), encoding="utf-8")
    return json_path, markdown_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate stored predictions with walk-forward champion gates.")
    parser.add_argument("--db", default=str(PROJECT_ROOT / "data" / "local_stage2.db"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--min-sample", type=int, default=20)
    parser.add_argument("--group-min-sample", type=int, default=5)
    parser.add_argument("--max-group-regression", type=float, default=0.02)
    parser.add_argument("--champion-label", default="current_fusion")
    parser.add_argument("--paired-champion-label", default="snapshot_adjusted")
    parser.add_argument(
        "--paired-baselines",
        default="uniform_baseline,dc_only,elo_only,tabular_only,pi_only,market_only,weibull_only",
        help="Comma-separated paired baselines. Comparisons are made only inside the same evaluation example.",
    )
    parser.add_argument("--enforce-gate", action="store_true", help="Exit non-zero when the champion gate fails.")
    parser.add_argument(
        "--enforce-paired-gate",
        action="store_true",
        help="Exit non-zero when the paired champion gate fails.",
    )
    parser.add_argument("--report-dir", default=str(PROJECT_ROOT / "reports"))
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--markdown-out", default=None)
    args = parser.parse_args(argv)
    paired_baselines = _parse_label_list(args.paired_baselines)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        report = build_walk_forward_report(
            conn=conn,
            db_path=args.db,
            limit=args.limit,
            min_sample=args.min_sample,
            group_min_sample=args.group_min_sample,
            max_group_regression=args.max_group_regression,
            champion_label=args.champion_label,
            paired_champion_label=args.paired_champion_label,
            paired_baselines=paired_baselines,
        )
    finally:
        conn.close()

    _print_summary(report, min_sample=args.min_sample)
    json_path, markdown_path = _write_reports(
        report,
        report_dir=Path(args.report_dir),
        json_out=args.json_out,
        markdown_out=args.markdown_out,
        min_sample=args.min_sample,
    )
    print(f"\nJSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")

    if report["loaded"]["current_fusion_evaluated"] < args.min_sample:
        print(
            f"\nFAIL: only {report['loaded']['current_fusion_evaluated']} current_fusion rows; "
            f"need at least {args.min_sample}."
        )
        return 2
    if args.enforce_gate and report["gate"]["status"] != "pass":
        print("\nFAIL: champion gate rejected current champion.")
        return 2
    if args.enforce_paired_gate and report["paired"]["gate"]["status"] != "pass":
        print("\nFAIL: paired gate rejected paired champion.")
        return 2
    print("\nOK: walk-forward report generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from collections import defaultdict

from app.services.evaluation_metrics import ThreeWayMetrics
from scripts.walk_forward_backtest import (
    Aggregate,
    EvaluationExample,
    GateConfig,
    build_paired_report,
    decide_champion_gate,
)


def _metric(*, log_loss: float, brier: float, rps: float, correct: bool = False) -> ThreeWayMetrics:
    return ThreeWayMetrics(brier=brier, log_loss=log_loss, rps=rps, correct=correct)


def _agg(*, n: int, log_loss: float, brier: float, rps: float, accuracy: float = 0.5) -> Aggregate:
    return Aggregate(
        n=n,
        log_loss=log_loss * n,
        brier=brier * n,
        rps=rps * n,
        correct=round(accuracy * n),
    )


def _config() -> GateConfig:
    return GateConfig(
        champion_label="current_fusion",
        min_sample=10,
        group_min_sample=5,
        max_group_regression=0.02,
    )


def _example(
    example_id: str,
    scores: dict[str, ThreeWayMetrics],
    *,
    horizon: str = "t_minus_24h",
    competition: str = "FIFA World Cup",
    run_type: str = "scheduled",
) -> EvaluationExample:
    return EvaluationExample(
        example_id=example_id,
        source="prediction_snapshots",
        prediction_id=example_id,
        match_id=f"match-{example_id}",
        as_of_time="2026-06-01T00:00:00Z",
        horizon=horizon,
        competition=competition,
        run_type=run_type,
        model_version="test",
        scores=scores,
    )


def _paired_report(examples: list[EvaluationExample], *, min_sample: int = 2):
    return build_paired_report(
        examples,
        paired_champion_label="snapshot_adjusted",
        paired_baselines=["uniform_baseline", "dc_only"],
        min_sample=min_sample,
        group_min_sample=2,
        max_group_regression=0.02,
    )


def test_champion_gate_passes_when_champion_beats_uniform_and_leads():
    leaderboard = {
        "current_fusion": _agg(n=20, log_loss=0.90, brier=0.50, rps=0.20),
        "uniform_baseline": _agg(n=20, log_loss=1.09, brier=0.66, rps=0.24),
        "dc_only": _agg(n=20, log_loss=0.95, brier=0.55, rps=0.21),
    }

    decision = decide_champion_gate(
        leaderboard=leaderboard,
        by_horizon={},
        by_competition={},
        by_run_type={},
        config=_config(),
    )

    assert decision["status"] == "pass"
    assert decision["leader_label"] == "current_fusion"


def test_champion_gate_fails_when_uniform_is_better():
    leaderboard = {
        "current_fusion": _agg(n=20, log_loss=1.20, brier=0.70, rps=0.25),
        "uniform_baseline": _agg(n=20, log_loss=1.09, brier=0.66, rps=0.24),
    }

    decision = decide_champion_gate(
        leaderboard=leaderboard,
        by_horizon={},
        by_competition={},
        by_run_type={},
        config=_config(),
    )

    assert decision["status"] == "fail"
    assert "champion log_loss is not better than uniform_baseline" in decision["reasons"]


def test_champion_gate_fails_on_critical_group_regression():
    leaderboard = {
        "current_fusion": _agg(n=20, log_loss=0.90, brier=0.50, rps=0.20),
        "uniform_baseline": _agg(n=20, log_loss=1.09, brier=0.66, rps=0.24),
    }
    by_horizon = defaultdict(Aggregate)
    by_horizon["t_minus_24h::current_fusion"] = _agg(n=8, log_loss=1.20, brier=0.70, rps=0.25)
    by_horizon["t_minus_24h::uniform_baseline"] = _agg(n=8, log_loss=1.09, brier=0.66, rps=0.24)

    decision = decide_champion_gate(
        leaderboard=leaderboard,
        by_horizon=by_horizon,
        by_competition={},
        by_run_type={},
        config=_config(),
    )

    assert decision["status"] == "fail"
    assert decision["group_regressions"]


def test_paired_gate_only_compares_labels_inside_same_example():
    examples = [
        _example("candidate-only", {"snapshot_adjusted": _metric(log_loss=0.1, brier=0.1, rps=0.1)}),
        _example("baseline-only", {"uniform_baseline": _metric(log_loss=1.0, brier=0.6, rps=0.3)}),
    ]

    report = _paired_report(examples, min_sample=1)

    comparison = report["comparisons"]["uniform_baseline"]
    assert comparison["status"] == "insufficient_samples"
    assert comparison["available_n"] == 0
    assert report["gate"]["status"] == "fail"


def test_paired_gate_does_not_create_false_comparison_when_candidate_missing():
    examples = [
        _example("missing-candidate", {"uniform_baseline": _metric(log_loss=1.0, brier=0.6, rps=0.3)}),
        _example("paired", {
            "snapshot_adjusted": _metric(log_loss=0.9, brier=0.5, rps=0.2),
            "uniform_baseline": _metric(log_loss=1.0, brier=0.6, rps=0.3),
        }),
    ]

    report = _paired_report(examples, min_sample=2)

    comparison = report["comparisons"]["uniform_baseline"]
    assert comparison["status"] == "insufficient_samples"
    assert comparison["available_n"] == 1


def test_paired_gate_fails_when_candidate_loses_to_uniform():
    examples = [
        _example("a", {
            "snapshot_adjusted": _metric(log_loss=1.3, brier=0.7, rps=0.4),
            "uniform_baseline": _metric(log_loss=1.1, brier=0.6, rps=0.3),
        }),
        _example("b", {
            "snapshot_adjusted": _metric(log_loss=1.4, brier=0.8, rps=0.5),
            "uniform_baseline": _metric(log_loss=1.1, brier=0.6, rps=0.3),
        }),
    ]

    report = _paired_report(examples)

    assert report["gate"]["status"] == "fail"
    assert "paired champion log_loss is not better than uniform_baseline" in report["gate"]["reasons"]
    assert "paired champion brier is not better than uniform_baseline" in report["gate"]["reasons"]


def test_paired_gate_fails_even_when_unpaired_candidate_examples_look_better():
    examples = [
        _example("candidate-only-a", {"snapshot_adjusted": _metric(log_loss=0.1, brier=0.1, rps=0.1)}),
        _example("candidate-only-b", {"snapshot_adjusted": _metric(log_loss=0.1, brier=0.1, rps=0.1)}),
        _example("paired-a", {
            "snapshot_adjusted": _metric(log_loss=1.4, brier=0.8, rps=0.5),
            "uniform_baseline": _metric(log_loss=1.1, brier=0.6, rps=0.3),
        }),
        _example("paired-b", {
            "snapshot_adjusted": _metric(log_loss=1.4, brier=0.8, rps=0.5),
            "uniform_baseline": _metric(log_loss=1.1, brier=0.6, rps=0.3),
        }),
    ]

    report = _paired_report(examples)

    comparison = report["comparisons"]["uniform_baseline"]
    assert comparison["status"] == "evaluated"
    assert comparison["n"] == 2
    assert comparison["candidate"]["log_loss"] > comparison["baseline"]["log_loss"]
    assert report["gate"]["status"] == "fail"


def test_paired_gate_marks_non_required_baseline_insufficient_without_failing_on_it():
    examples = [
        _example("a", {
            "snapshot_adjusted": _metric(log_loss=0.8, brier=0.5, rps=0.2),
            "uniform_baseline": _metric(log_loss=1.1, brier=0.6, rps=0.3),
            "dc_only": _metric(log_loss=0.9, brier=0.5, rps=0.2),
        }),
        _example("b", {
            "snapshot_adjusted": _metric(log_loss=0.8, brier=0.5, rps=0.2),
            "uniform_baseline": _metric(log_loss=1.1, brier=0.6, rps=0.3),
        }),
    ]

    report = _paired_report(examples)

    assert report["comparisons"]["dc_only"]["status"] == "insufficient_samples"
    assert report["insufficient_baselines"]["dc_only"]["available_n"] == 1
    assert report["gate"]["status"] == "pass"

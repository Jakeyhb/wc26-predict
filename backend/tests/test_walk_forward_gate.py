from __future__ import annotations

from collections import defaultdict

from scripts.walk_forward_backtest import Aggregate, GateConfig, decide_champion_gate


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

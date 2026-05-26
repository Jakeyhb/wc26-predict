from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.services.dixon_coles import DixonColesModel


def build_model() -> DixonColesModel:
    model = DixonColesModel()
    model.attack_params = {"Argentina": 1.18, "France": 1.11, "Brazil": 1.2}
    model.defense_params = {"Argentina": 0.92, "France": 0.95, "Brazil": 0.88}
    model.home_advantage = 0.14
    model.rho = -0.08
    return model


def build_training_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"match_date": "2022-11-20T18:00:00Z", "home_team": "Argentina", "away_team": "France", "home_goals": 2, "away_goals": 1, "competition_weight": 1.0, "is_neutral_venue": True},
            {"match_date": "2022-11-25T18:00:00Z", "home_team": "France", "away_team": "Brazil", "home_goals": 1, "away_goals": 1, "competition_weight": 1.0, "is_neutral_venue": True},
            {"match_date": "2023-01-10T18:00:00Z", "home_team": "Brazil", "away_team": "Argentina", "home_goals": 3, "away_goals": 2, "competition_weight": 0.7, "is_neutral_venue": False},
            {"match_date": "2023-03-12T18:00:00Z", "home_team": "Argentina", "away_team": "Brazil", "home_goals": 1, "away_goals": 0, "competition_weight": 0.7, "is_neutral_venue": False},
            {"match_date": "2023-05-12T18:00:00Z", "home_team": "France", "away_team": "Argentina", "home_goals": 0, "away_goals": 1, "competition_weight": 0.7, "is_neutral_venue": False},
            {"match_date": "2023-07-18T18:00:00Z", "home_team": "Brazil", "away_team": "France", "home_goals": 2, "away_goals": 1, "competition_weight": 0.7, "is_neutral_venue": False},
            {"match_date": "2023-09-08T18:00:00Z", "home_team": "Argentina", "away_team": "France", "home_goals": 1, "away_goals": 1, "competition_weight": 0.7, "is_neutral_venue": True},
            {"match_date": "2023-10-12T18:00:00Z", "home_team": "France", "away_team": "Brazil", "home_goals": 0, "away_goals": 2, "competition_weight": 0.7, "is_neutral_venue": True},
            {"match_date": "2024-01-15T18:00:00Z", "home_team": "Brazil", "away_team": "Argentina", "home_goals": 1, "away_goals": 1, "competition_weight": 0.7, "is_neutral_venue": False},
            {"match_date": "2024-03-09T18:00:00Z", "home_team": "Argentina", "away_team": "Brazil", "home_goals": 2, "away_goals": 0, "competition_weight": 0.7, "is_neutral_venue": False},
            {"match_date": "2024-05-18T18:00:00Z", "home_team": "France", "away_team": "Argentina", "home_goals": 1, "away_goals": 2, "competition_weight": 0.7, "is_neutral_venue": True},
            {"match_date": "2024-06-21T18:00:00Z", "home_team": "Brazil", "away_team": "France", "home_goals": 2, "away_goals": 2, "competition_weight": 0.7, "is_neutral_venue": True},
        ]
    )


def test_time_weight_same_day_is_one() -> None:
    model = build_model()
    assert model._time_weight(date(2026, 6, 1), date(2026, 6, 1)) == pytest.approx(1.0)


def test_time_weight_decays_over_time() -> None:
    model = build_model()
    recent = model._time_weight(date(2026, 5, 25), date(2026, 6, 1))
    old = model._time_weight(date(2025, 6, 1), date(2026, 6, 1))
    assert recent > old


def test_tau_adjusts_low_scores_only() -> None:
    model = build_model()
    assert model._tau(0, 0, 1.2, 0.9, -0.05) == pytest.approx(1 - (1.2 * 0.9 * -0.05))
    assert model._tau(2, 2, 1.2, 0.9, -0.05) == pytest.approx(1.0)


def test_predict_score_matrix_shape() -> None:
    model = build_model()
    matrix = model.predict_score_matrix("Argentina", "France", is_neutral_venue=True, max_goals=4)
    assert matrix.shape == (5, 5)


def test_predict_score_matrix_sums_to_one() -> None:
    model = build_model()
    matrix = model.predict_score_matrix("Argentina", "France", is_neutral_venue=True)
    assert matrix.sum() == pytest.approx(1.0, rel=1e-6)


def test_predict_match_probabilities_sum_to_one() -> None:
    model = build_model()
    prediction = model.predict_match("Argentina", "France")
    total = prediction["home_win_prob"] + prediction["draw_prob"] + prediction["away_win_prob"]
    assert total == pytest.approx(1.0, rel=1e-6)


def test_predict_match_top3_are_sorted() -> None:
    model = build_model()
    prediction = model.predict_match("Argentina", "France")
    probs = [item["prob"] for item in prediction["top3_scores"]]
    assert probs == sorted(probs, reverse=True)


def test_home_advantage_changes_non_neutral_prediction() -> None:
    model = build_model()
    neutral = model.predict_match("Brazil", "France", is_neutral_venue=True)
    home = model.predict_match("Brazil", "France", is_neutral_venue=False)
    assert home["home_win_prob"] != pytest.approx(neutral["home_win_prob"])


def test_predict_match_unknown_team_raises() -> None:
    model = build_model()
    with pytest.raises(KeyError):
        model.predict_match("Unknown", "France")


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    model = build_model()
    target = tmp_path / "model.json"
    model.save(str(target))

    restored = DixonColesModel()
    restored.load(str(target))

    assert restored.attack_params == model.attack_params
    assert restored.defense_params == model.defense_params
    assert restored.home_advantage == model.home_advantage
    assert restored.rho == model.rho


def test_fit_populates_parameters() -> None:
    model = DixonColesModel()
    summary = model.fit(build_training_df())

    assert summary.parameter_count > 0
    assert len(model.attack_params) == 3
    assert len(model.defense_params) == 3
    assert model.trained_at is not None


def test_evaluate_returns_expected_metrics() -> None:
    model = DixonColesModel()
    training_df = build_training_df()
    model.fit(training_df)
    evaluation = model.evaluate(training_df.iloc[-4:].copy())

    assert "brier_score" in evaluation
    assert "log_loss" in evaluation
    assert "calibration" in evaluation
    assert 0 <= evaluation["exact_score_hit_rate"] <= 1
    assert 0 <= evaluation["top3_hit_rate"] <= 1

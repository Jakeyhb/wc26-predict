from __future__ import annotations

import math

from app.services.evaluation_metrics import (
    brier_score,
    evaluate_three_way,
    log_loss,
    normalize_probs,
    outcome_index,
    ranked_probability_score,
)


def test_outcome_index():
    assert outcome_index(2, 0) == 0
    assert outcome_index(1, 1) == 1
    assert outcome_index(0, 2) == 2


def test_normalize_probs():
    assert normalize_probs(2, 1, 1) == (0.5, 0.25, 0.25)
    assert normalize_probs(0, 0, 0) == (1 / 3, 1 / 3, 1 / 3)


def test_brier_and_log_loss_for_perfect_prediction():
    probs = (1.0, 0.0, 0.0)
    assert brier_score(probs, 0) == 0.0
    assert math.isclose(log_loss(probs, 0), 0.0, abs_tol=1e-9)


def test_ranked_probability_score_for_perfect_prediction():
    assert ranked_probability_score((1.0, 0.0, 0.0), 0) == 0.0


def test_evaluate_three_way_bundle():
    metrics = evaluate_three_way(
        home_prob=0.6,
        draw_prob=0.25,
        away_prob=0.15,
        home_goals=2,
        away_goals=1,
    )
    assert metrics.correct is True
    assert metrics.log_loss > 0
    assert metrics.brier > 0
    assert metrics.rps > 0

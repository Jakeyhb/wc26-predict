"""Proper scoring metrics for three-way football predictions."""

from __future__ import annotations

import math
from dataclasses import dataclass


OUTCOME_KEYS = ("home", "draw", "away")


@dataclass(frozen=True)
class ThreeWayMetrics:
    """Metric bundle for one 1X2 probability prediction."""

    brier: float
    log_loss: float
    rps: float
    correct: bool


def outcome_index(home_goals: int, away_goals: int) -> int:
    """Return 0=home win, 1=draw, 2=away win."""
    if home_goals > away_goals:
        return 0
    if home_goals == away_goals:
        return 1
    return 2


def normalize_probs(home: float, draw: float, away: float) -> tuple[float, float, float]:
    """Clip and normalize probabilities without silently accepting bad sums."""
    values = [max(float(home), 0.0), max(float(draw), 0.0), max(float(away), 0.0)]
    total = sum(values)
    if total <= 0:
        return (1 / 3, 1 / 3, 1 / 3)
    return (values[0] / total, values[1] / total, values[2] / total)


def brier_score(probs: tuple[float, float, float], actual_index: int) -> float:
    """Multiclass Brier score using the unscaled sum convention."""
    return sum((prob - (1.0 if idx == actual_index else 0.0)) ** 2 for idx, prob in enumerate(probs))


def log_loss(probs: tuple[float, float, float], actual_index: int, eps: float = 1e-12) -> float:
    """Negative log probability assigned to the realised result."""
    return -math.log(max(min(probs[actual_index], 1.0 - eps), eps))


def ranked_probability_score(probs: tuple[float, float, float], actual_index: int) -> float:
    """RPS for the ordered 1X2 vector [home, draw, away]."""
    score = 0.0
    pred_cum = 0.0
    actual_cum = 0.0
    for idx, prob in enumerate(probs):
        pred_cum += prob
        actual_cum += 1.0 if idx == actual_index else 0.0
        score += (pred_cum - actual_cum) ** 2
    return score / 2.0


def evaluate_three_way(
    *,
    home_prob: float,
    draw_prob: float,
    away_prob: float,
    home_goals: int,
    away_goals: int,
) -> ThreeWayMetrics:
    """Evaluate a single three-way prediction against a final score."""
    probs = normalize_probs(home_prob, draw_prob, away_prob)
    actual = outcome_index(home_goals, away_goals)
    predicted = max(range(3), key=lambda idx: probs[idx])
    return ThreeWayMetrics(
        brier=brier_score(probs, actual),
        log_loss=log_loss(probs, actual),
        rps=ranked_probability_score(probs, actual),
        correct=predicted == actual,
    )

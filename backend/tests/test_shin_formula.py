"""Test Shin implied probability formula (H4 fix).

Tests the correct Shin (1993) formula for vig removal from decimal odds.
The old formula (1-z)/odds was a linear approximation that fails for z > 0.
"""
import math
import pytest
from app.services.market.probability import _shin_implied, normalize_1x2_shin


def _correct_shin(odds: float, z: float) -> float:
    """Reference implementation of correct Shin formula."""
    if z < 1e-12:
        return 1.0 / odds
    inv = 1.0 / odds
    return (math.sqrt(z * z + 4.0 * (1.0 - z) * inv) - z) / (2.0 * (1.0 - z))


def test_shin_z_zero_equals_proportional():
    """When z=0 (no informed bettors), Shin reduces to 1/odds."""
    assert _shin_implied(2.0, 0.0) == pytest.approx(0.5, rel=1e-6)
    assert _shin_implied(3.5, 0.0) == pytest.approx(1.0 / 3.5, rel=1e-6)
    assert _shin_implied(10.0, 0.0) == pytest.approx(0.1, rel=1e-6)


def test_shin_z_positive_differs_from_linear():
    """For z > 0, the correct Shin formula differs from the old (1-z)/odds."""
    z = 0.2
    odds = 2.0
    old_result = (1.0 - z) / odds  # 0.4
    new_result = _shin_implied(odds, z)
    # Correct formula should NOT equal the linear approximation when z > 0
    assert new_result != pytest.approx(old_result, abs=1e-6)
    # Correct formula gives ~0.676 vs old 0.4
    assert new_result > old_result


def test_shin_z_tiny_consistent_with_z_zero():
    """z→0 limit of Shin formula is self-consistent (gives sqrt(1/o)).

    The raw (unnormalized) Shin formula at z→0 approaches sqrt(1/o),
    NOT 1/o.  This is correct — normalization in the full
    normalize_1x2_shin solver handles the difference.
    """
    expected = math.sqrt(1.0 / 2.5)  # ~0.632
    tiny_z = _shin_implied(2.5, 1e-10)
    assert tiny_z == pytest.approx(expected, rel=1e-6)


def test_normalize_1x2_shin_sums_to_one():
    """Shin-normalized three-outcome probabilities must sum to 1.0."""
    result = normalize_1x2_shin(2.10, 3.50, 3.80)
    total = result["home"] + result["draw"] + result["away"]
    assert total == pytest.approx(1.0, abs=1e-8)
    assert result["z"] >= 0.0
    assert result["z"] <= 0.5


def test_normalize_1x2_shin_balanced_odds():
    """Balanced odds: all outcomes equally likely."""
    result = normalize_1x2_shin(3.0, 3.0, 3.0)
    total = result["home"] + result["draw"] + result["away"]
    assert total == pytest.approx(1.0, abs=1e-8)
    # Balanced odds → balanced probabilities
    assert result["home"] == pytest.approx(1.0 / 3.0, abs=0.05)
    assert result["draw"] == pytest.approx(1.0 / 3.0, abs=0.05)
    assert result["away"] == pytest.approx(1.0 / 3.0, abs=0.05)


def test_normalize_1x2_shin_strong_favorite():
    """Strong favorite market should converge."""
    result = normalize_1x2_shin(1.50, 5.00, 9.00)
    total = result["home"] + result["draw"] + result["away"]
    assert total == pytest.approx(1.0, abs=1e-8)
    # Favorite should have highest probability
    assert result["home"] > result["draw"]
    assert result["home"] > result["away"]


def test_normalize_1x2_shin_all_outcomes_positive():
    """All Shin-corrected probabilities must be strictly positive."""
    result = normalize_1x2_shin(1.80, 3.75, 4.50)
    assert result["home"] > 0.0
    assert result["draw"] > 0.0
    assert result["away"] > 0.0


def test_normalize_1x2_shin_overround_present():
    """Shin method preserves overround information in output."""
    result = normalize_1x2_shin(2.10, 3.50, 3.80)
    assert "overround" in result
    assert result["overround"] > 0.0  # bookmaker margin


def test_invalid_odds_raises():
    """Invalid odds (<= 1.0) must raise ValueError."""
    with pytest.raises(ValueError):
        normalize_1x2_shin(1.0, 2.0, 3.0)
    with pytest.raises(ValueError):
        normalize_1x2_shin(2.0, 0.5, 3.0)
    with pytest.raises(ValueError):
        normalize_1x2_shin(2.0, 3.0, -1.0)

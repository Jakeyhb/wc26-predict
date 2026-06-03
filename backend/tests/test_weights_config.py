"""Test unified weight configuration from weights.py.

Note: get_weight_config() may return DB-auto-optimized weights
(AUTO_OPTIMIZED label) when available, which override code defaults.
Tests for specific competition defaults use WeightConfig dataclass directly
or test value ranges when going through get_weight_config().
"""
from __future__ import annotations

import pytest
from app.services.weights import (
    WeightConfig,
    get_weight_config,
    get_world_cup_weights,
)


def test_weight_config_defaults():
    """Default WeightConfig has sensible values."""
    wc = WeightConfig()
    assert 0.0 < wc.dc < 1.0
    assert 0.0 < wc.enhancer < 1.0
    assert 0.0 < wc.elo < 1.0
    assert 0.0 < wc.pi < 1.0
    assert wc.active is True
    assert wc.label == "DEFAULT"


def test_weight_config_immutable_values():
    """Key weights are within valid ranges."""
    wc = WeightConfig()
    total = wc.dc + wc.elo + wc.pi + wc.weibull
    # Sum of additive weights typically < 0.8 (leaving room for enhancer + market)
    assert total < 1.0


def test_world_cup_weights_valid():
    """World Cup returns a valid WeightConfig (exact values may vary due to DB)."""
    config = get_weight_config("FIFA World Cup 2026", "Group A - Matchday 1")
    assert 0.4 < config.dc < 0.7  # DB may override code default 0.55
    assert 0.0 < config.elo < 0.2
    assert config.active is True


def test_league_default_valid():
    """Unknown competition returns a valid config."""
    config = get_weight_config("Some Unknown League")
    assert config.active is True
    assert 0.0 < config.dc < 1.0
    assert 0.0 < config.elo < 1.0


def test_ucl_final_valid():
    """UCL final returns a valid WeightConfig."""
    config = get_weight_config("UEFA Champions League", "Final")
    assert 0.0 < config.dc < 1.0
    assert config.active is True


def test_get_world_cup_weights_convenience():
    """Convenience function returns a valid WeightConfig."""
    wc = get_world_cup_weights()
    assert wc.active is True
    assert 0.0 < wc.dc < 1.0


def test_weight_config_to_dict():
    """to_dict() serializes all fields."""
    wc = WeightConfig(dc=0.6, label="test")
    d = wc.to_dict()
    assert d["dc"] == 0.6
    assert d["label"] == "test"
    assert "version" in d


def test_weight_config_dc_enhancer_blend():
    """dc_enhancer_blend property returns dc value."""
    wc = WeightConfig(dc=0.55)
    assert wc.dc_enhancer_blend == 0.55
    assert wc.enhancer_complement == pytest.approx(0.45)

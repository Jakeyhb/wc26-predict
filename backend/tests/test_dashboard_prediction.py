"""test_dashboard_prediction.py — Dashboard → PredictionCore integration tests."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from app.services.prediction_core import run_artifact_pipeline


class TestPredictionCore:
    """Test prediction_core works correctly for Dashboard integration."""

    def test_full_mode_returns_dict(self):
        result, quality, timer = run_artifact_pipeline(
            home_team="France",
            away_team="Ivory Coast",
            competition="International Friendly",
            is_neutral=True,
            mode="full",
        )
        assert isinstance(result, dict)
        assert "home_win_prob" in result
        assert "draw_prob" in result
        assert "away_win_prob" in result
        assert "home_xg" in result
        assert "away_xg" in result
        assert "components_used" in result
        assert "fusion_graph" in result

    def test_probabilities_sum_to_one(self):
        result, _, _ = run_artifact_pipeline(
            home_team="France",
            away_team="Ivory Coast",
            competition="International Friendly",
            is_neutral=True,
            mode="full",
        )
        total = (
            result["home_win_prob"]
            + result["draw_prob"]
            + result["away_win_prob"]
        )
        assert abs(total - 1.0) < 0.01, f"Probabilities sum to {total}"

    def test_all_probabilities_in_range(self):
        result, _, _ = run_artifact_pipeline(
            home_team="France",
            away_team="Ivory Coast",
            competition="International Friendly",
            is_neutral=True,
            mode="full",
        )
        for key in ["home_win_prob", "draw_prob", "away_win_prob"]:
            assert 0.0 <= result[key] <= 1.0, f"{key} out of range: {result[key]}"

    def test_components_loaded_from_artifact(self):
        _, quality, _ = run_artifact_pipeline(
            home_team="France",
            away_team="Ivory Coast",
            competition="International Friendly",
            is_neutral=True,
            mode="full",
        )
        # Core components should be from artifact
        for comp in ["dixon_coles", "tabular_enhancer", "elo", "pi_rating"]:
            status = quality.model_components.get(comp)
            assert status == "loaded_from_artifact", (
                f"{comp} status is {status}, expected loaded_from_artifact"
            )

    def test_deterministic_output(self):
        """Same inputs produce same outputs (no randomness in artifact inference)."""
        r1, _, _ = run_artifact_pipeline(
            home_team="Brazil",
            away_team="Argentina",
            competition="FIFA World Cup 2026",
            is_neutral=True,
            mode="full",
        )
        r2, _, _ = run_artifact_pipeline(
            home_team="Brazil",
            away_team="Argentina",
            competition="FIFA World Cup 2026",
            is_neutral=True,
            mode="full",
        )
        assert r1["home_win_prob"] == r2["home_win_prob"]
        assert r1["draw_prob"] == r2["draw_prob"]
        assert r1["away_win_prob"] == r2["away_win_prob"]

    def test_baseline_mode(self):
        result, quality, _ = run_artifact_pipeline(
            home_team="France",
            away_team="Ivory Coast",
            competition="International Friendly",
            is_neutral=True,
            mode="baseline",
        )
        assert "dixon_coles" in result["components_used"]
        # baseline should not include enhancer, elo, or pi
        for comp in ["tabular_enhancer", "elo", "pi_rating"]:
            assert comp not in result["components_used"]

    def test_standard_mode(self):
        result, quality, _ = run_artifact_pipeline(
            home_team="France",
            away_team="Ivory Coast",
            competition="International Friendly",
            is_neutral=True,
            mode="standard",
        )
        for comp in ["dixon_coles", "tabular_enhancer", "elo"]:
            assert comp in result["components_used"]

    def test_fusion_graph_present(self):
        result, _, _ = run_artifact_pipeline(
            home_team="France",
            away_team="Ivory Coast",
            competition="International Friendly",
            is_neutral=True,
            mode="full",
        )
        fg = result["fusion_graph"]
        assert "method" in fg
        assert fg["method"] == "sequential_blend"
        assert "effective_weights" in fg
        assert "steps" in fg
        assert len(fg["steps"]) >= 3  # dc+enhancer, +elo, +pi

    def test_pipeline_status_full(self):
        _, quality, _ = run_artifact_pipeline(
            home_team="France",
            away_team="Ivory Coast",
            competition="International Friendly",
            is_neutral=True,
            mode="full",
        )
        assert quality.pipeline_status == "full", (
            f"Expected 'full', got '{quality.pipeline_status}'"
        )

    def test_run_quality_has_warnings_field(self):
        _, quality, _ = run_artifact_pipeline(
            home_team="France",
            away_team="Ivory Coast",
            competition="International Friendly",
            is_neutral=True,
            mode="full",
        )
        assert hasattr(quality, "warnings")
        assert isinstance(quality.warnings, list)

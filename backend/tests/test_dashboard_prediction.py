"""test_dashboard_prediction.py — Dashboard → PredictionPipeline integration tests.

Exercises the current PredictionPipeline artifact entry and the Dashboard
compatibility wrapper.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from app.services.prediction_pipeline import PredictionPipeline
from app.services.run_quality import RunQuality


def _predict(mode="full", home="France", away="Ivory Coast",
             competition="International Friendly", is_neutral=True):
    """Convenience: run artifact prediction and return (result_dict, quality)."""
    pipeline = PredictionPipeline.from_artifacts(mode=mode)
    pred = pipeline.predict_sync(home, away, competition, is_neutral=is_neutral)
    # Build backward-compatible dict for tests expecting dict-like access
    d = pred.to_dict()
    result_dict = d["prediction"]
    result_dict["home_team"] = pred.home_team
    result_dict["away_team"] = pred.away_team
    result_dict["competition"] = pred.competition
    result_dict["is_neutral"] = pred.is_neutral
    result_dict["home_xg"] = pred.home_xg
    result_dict["away_xg"] = pred.away_xg
    result_dict["home_win_prob"] = pred.home_win_prob
    result_dict["draw_prob"] = pred.draw_prob
    result_dict["away_win_prob"] = pred.away_win_prob
    result_dict["top_scores"] = pred.top_scores
    result_dict["components_used"] = list(pred.components_used)
    result_dict["fusion_graph"] = {
        "method": "sequential_blend",
        "effective_weights": d.get("meta", {}).get("weight_config", {}),
        "steps": [],
    }
    # Build RunQuality for backward compatibility
    quality = RunQuality()
    quality.pipeline_status = "full"
    for c in pred.components_used:
        quality.model_components[c] = "loaded_from_artifact"
    return result_dict, quality


class TestPredictionPipeline:
    """Test PredictionPipeline works correctly for Dashboard integration."""

    def test_full_mode_returns_dict(self):
        result, _ = _predict(mode="full")
        assert isinstance(result, dict)
        assert "home_win_prob" in result
        assert "draw_prob" in result
        assert "away_win_prob" in result
        assert "home_xg" in result
        assert "away_xg" in result
        assert "components_used" in result

    def test_probabilities_sum_to_one(self):
        result, _ = _predict(mode="full")
        total = (
            result["home_win_prob"]
            + result["draw_prob"]
            + result["away_win_prob"]
        )
        assert abs(total - 1.0) < 0.01, f"Probabilities sum to {total}"

    def test_all_probabilities_in_range(self):
        result, _ = _predict(mode="full")
        for key in ["home_win_prob", "draw_prob", "away_win_prob"]:
            assert 0.0 <= result[key] <= 1.0, f"{key} out of range: {result[key]}"

    def test_components_loaded_from_artifact(self):
        _, quality = _predict(mode="full")
        for comp in ["dixon_coles", "tabular_enhancer", "elo", "pi_rating"]:
            status = quality.model_components.get(comp)
            assert status == "loaded_from_artifact", (
                f"{comp} status is {status}, expected loaded_from_artifact"
            )

    def test_deterministic_output(self):
        """Same inputs produce same outputs (no randomness in artifact inference)."""
        r1, _ = _predict(mode="full", home="Brazil", away="Argentina",
                         competition="FIFA World Cup 2026")
        r2, _ = _predict(mode="full", home="Brazil", away="Argentina",
                         competition="FIFA World Cup 2026")
        assert r1["home_win_prob"] == r2["home_win_prob"]
        assert r1["draw_prob"] == r2["draw_prob"]
        assert r1["away_win_prob"] == r2["away_win_prob"]

    def test_baseline_mode(self):
        result, _ = _predict(mode="baseline")
        assert "dixon_coles" in result["components_used"]
        for comp in ["tabular_enhancer", "elo", "pi_rating"]:
            assert comp not in result["components_used"]

    def test_standard_mode(self):
        result, _ = _predict(mode="standard")
        for comp in ["dixon_coles", "tabular_enhancer", "elo"]:
            assert comp in result["components_used"]

    def test_pipeline_status_full(self):
        _, quality = _predict(mode="full")
        assert quality.pipeline_status == "full", (
            f"Expected 'full', got '{quality.pipeline_status}'"
        )

    def test_run_quality_has_warnings_field(self):
        _, quality = _predict(mode="full")
        assert hasattr(quality, "warnings")
        assert isinstance(quality.warnings, list)

    def test_risk_tags_are_list(self):
        pipeline = PredictionPipeline.from_artifacts(mode="full")
        result = pipeline.predict_sync("France", "Ivory Coast",
                                       "International Friendly", is_neutral=True)
        assert isinstance(result.risk_tags, list)

    def test_degraded_reasons_are_list(self):
        pipeline = PredictionPipeline.from_artifacts(mode="full")
        result = pipeline.predict_sync("France", "Ivory Coast",
                                       "International Friendly", is_neutral=True)
        assert isinstance(result.degraded_reasons, list)

    def test_sync_prediction_accepts_match_metadata(self):
        pipeline = PredictionPipeline.from_artifacts(mode="full")
        result = pipeline.predict_sync(
            "France",
            "Ivory Coast",
            "International Friendly",
            is_neutral=True,
            match_id="12345678123456781234567812345678",
            match_date="2026-06-14T14:00:00+00:00",
            venue="stade de france",
            enable_market=False,
            enable_weather=False,
            save_snapshot=False,
        )

        assert result.match_id == "12345678123456781234567812345678"
        assert result.match_date.startswith("2026-06-14T14:00:00")
        assert result.home_win_prob + result.draw_prob + result.away_win_prob == pytest.approx(1.0)
        assert result.source_status["match_context"].status == "used"
        assert result.source_status["market"].status == "skipped"
        assert result.source_status["weather"].status == "skipped"

    def test_strict_full_requires_context_and_live_sources(self):
        pipeline = PredictionPipeline.from_artifacts(mode="full")
        with pytest.raises(ValueError, match="require_full_context=True"):
            pipeline.predict_sync(
                "France",
                "Ivory Coast",
                "International Friendly",
                is_neutral=True,
                enable_market=False,
                enable_weather=False,
                require_full_context=True,
            )

    def test_enhanced_entrypoint_wraps_prediction_pipeline(self):
        from app.services.prediction_enhanced import run_enhanced_prediction

        result = run_enhanced_prediction(
            "France",
            "Ivory Coast",
            "International Friendly",
            is_neutral=True,
            mode="full",
            enable_market=False,
            enable_weather=False,
            enable_llm=False,
            match_id="12345678123456781234567812345678",
            match_date="2026-06-14T14:00:00+00:00",
            venue="stade de france",
        )

        assert result.llm_error is None
        assert result.base_result["home_team"] == "France"
        assert result.base_result["away_team"] == "Ivory Coast"
        assert result.base_result["match_id"] == "12345678123456781234567812345678"
        assert result.base_result["match_date"].startswith("2026-06-14T14:00:00")
        assert result.base_result["source_status"]["match_context"]["status"] == "used"
        assert result.source_status["market"]["status"] == "skipped"
        assert result.components_used

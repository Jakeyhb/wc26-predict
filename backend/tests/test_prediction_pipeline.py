"""Tests for PredictionPipeline and RunQuality."""
from __future__ import annotations

import asyncio
import inspect

import pytest

from app.services.prediction_pipeline import PredictionPipeline
from app.services.run_quality import RunQuality


class TestPredictionPipeline:
    """Verify PredictionPipeline class structure."""

    def test_prediction_pipeline_has_predict_match(self) -> None:
        assert hasattr(PredictionPipeline, "predict_match")

    def test_prediction_pipeline_has_predict_alias(self) -> None:
        assert hasattr(PredictionPipeline, "predict")

    def test_predict_is_async_callable(self) -> None:
        assert asyncio.iscoroutinefunction(PredictionPipeline.predict)


class TestRunQuality:
    """Verify RunQuality dataclass behaviour."""

    def test_run_quality_creation(self) -> None:
        rq = RunQuality()
        assert rq.pipeline_status == "full"
        assert rq.model_components["dixon_coles"] == "skipped"
        assert rq.cache["dixon_coles"] == "miss"
        assert rq.fact_check == "skipped"
        assert rq.warnings == []

    def test_run_quality_degraded(self) -> None:
        rq = RunQuality()
        rq.mark_degraded("DC fit failed, using cached values")
        assert rq.pipeline_status == "degraded"
        assert "DC fit failed, using cached values" in rq.warnings

    def test_run_quality_to_dict(self) -> None:
        rq = RunQuality()
        rq.mark_degraded("No training data for competition")
        d = rq.to_dict()
        assert d["pipeline_status"] == "degraded"
        assert len(d["warnings"]) == 1
        assert d["warnings"][0] == "No training data for competition"
        assert isinstance(d["model_components"], dict)

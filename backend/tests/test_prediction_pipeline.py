"""Tests for PredictionPipeline, RunQuality, and degraded_reasons contract.

Ticket 1.2: prediction_pipeline contract strengthening.
"""
from __future__ import annotations

import asyncio
import inspect

import pytest

from app.services.prediction_pipeline import PredictionPipeline
from app.services.prediction_result import DegradedReason, PredictionResult
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


# ═══════════════════════════════════════════════════════════════════════════════
# Ticket 1.2: degraded_reasons contract tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDegradedReasonDataclass:
    """Verify DegradedReason structure and serialization."""

    def test_required_fields(self) -> None:
        dr = DegradedReason(
            source="pi_rating",
            reason="fitting_failed",
            severity="warning",
            detail="ZeroDivisionError",
        )
        assert dr.source == "pi_rating"
        assert dr.reason == "fitting_failed"
        assert dr.severity == "warning"
        assert dr.detail == "ZeroDivisionError"

    def test_default_severity_is_warning(self) -> None:
        dr = DegradedReason(source="weather", reason="api_timeout")
        assert dr.severity == "warning"

    def test_default_detail_is_empty(self) -> None:
        dr = DegradedReason(source="weather", reason="api_timeout")
        assert dr.detail == ""

    def test_to_dict_roundtrip(self) -> None:
        original = DegradedReason(
            source="market_calibration",
            reason="calibration_failed",
            severity="error",
            detail="Connection refused",
        )
        d = original.to_dict()
        restored = DegradedReason.from_dict(d)
        assert restored.source == original.source
        assert restored.reason == original.reason
        assert restored.severity == original.severity
        assert restored.detail == original.detail


class TestPredictionResultDegradedReasons:
    """Verify PredictionResult.degraded_reasons field contract."""

    def test_normal_prediction_has_empty_degraded_reasons(self) -> None:
        """Normal prediction (no failures) must have empty degraded_reasons."""
        result = PredictionResult(
            home_team="Argentina",
            away_team="Brazil",
            competition="FIFA World Cup 2026",
        )
        assert result.degraded_reasons == []
        assert isinstance(result.degraded_reasons, list)

    def test_one_source_missing(self) -> None:
        """Single data source failure must be recorded."""
        result = PredictionResult(
            home_team="Argentina",
            away_team="Brazil",
            competition="FIFA World Cup 2026",
            degraded_reasons=[
                DegradedReason(
                    source="pi_rating",
                    reason="fitting_failed",
                    severity="warning",
                    detail="ValueError: singular matrix",
                ),
            ],
        )
        assert len(result.degraded_reasons) == 1
        dr = result.degraded_reasons[0]
        assert dr.source == "pi_rating"
        assert dr.reason == "fitting_failed"
        assert dr.severity == "warning"

    def test_multiple_sources_missing(self) -> None:
        """Multiple data source failures must all be recorded."""
        result = PredictionResult(
            home_team="Argentina",
            away_team="Brazil",
            competition="FIFA World Cup 2026",
            degraded_reasons=[
                DegradedReason(
                    source="pi_rating",
                    reason="fitting_failed",
                    severity="warning",
                    detail="ValueError",
                ),
                DegradedReason(
                    source="market_calibration",
                    reason="api_unavailable",
                    severity="error",
                    detail="Connection timeout",
                ),
                DegradedReason(
                    source="context_adjuster",
                    reason="db_query_failed",
                    severity="warning",
                    detail="OperationalError",
                ),
            ],
        )
        assert len(result.degraded_reasons) == 3
        sources = {dr.source for dr in result.degraded_reasons}
        assert sources == {"pi_rating", "market_calibration", "context_adjuster"}

    def test_to_dict_includes_degraded_reasons(self) -> None:
        """to_dict() must serialize degraded_reasons."""
        result = PredictionResult(
            home_team="Argentina",
            away_team="Brazil",
            competition="FIFA World Cup 2026",
            degraded_reasons=[
                DegradedReason(
                    source="market_calibration",
                    reason="calibration_failed",
                    severity="warning",
                ),
            ],
        )
        d = result.to_dict()
        assert "degraded_reasons" in d
        assert len(d["degraded_reasons"]) == 1
        assert d["degraded_reasons"][0]["source"] == "market_calibration"
        assert d["degraded_reasons"][0]["reason"] == "calibration_failed"
        assert d["degraded_reasons"][0]["severity"] == "warning"

    def test_from_dict_restores_degraded_reasons(self) -> None:
        """from_dict() must round-trip degraded_reasons."""
        original = PredictionResult(
            home_team="Argentina",
            away_team="Brazil",
            competition="FIFA World Cup 2026",
            degraded_reasons=[
                DegradedReason(
                    source="weather",
                    reason="api_timeout",
                    severity="error",
                    detail="httpx.TimeoutException",
                ),
                DegradedReason(
                    source="pi_rating",
                    reason="fitting_failed",
                    severity="warning",
                ),
            ],
        )
        d = original.to_dict()
        restored = PredictionResult.from_dict(d)
        assert len(restored.degraded_reasons) == 2
        assert restored.degraded_reasons[0].source == "weather"
        assert restored.degraded_reasons[0].severity == "error"
        assert restored.degraded_reasons[1].source == "pi_rating"

    def test_empty_degraded_reasons_survives_roundtrip(self) -> None:
        """No degraded_reasons must round-trip as empty list, not None."""
        result = PredictionResult(
            home_team="Argentina",
            away_team="Brazil",
            competition="FIFA World Cup 2026",
        )
        d = result.to_dict()
        restored = PredictionResult.from_dict(d)
        assert restored.degraded_reasons == []

    def test_degraded_reasons_structure_is_stable(self) -> None:
        """Every degraded reason must have source, reason, severity keys."""
        result = PredictionResult(
            home_team="Argentina",
            away_team="Brazil",
            competition="FIFA World Cup 2026",
            degraded_reasons=[
                DegradedReason(source="x", reason="y", severity="warning"),
                DegradedReason(source="a", reason="b", severity="error"),
            ],
        )
        d = result.to_dict()
        for dr in d["degraded_reasons"]:
            required = {"source", "reason", "severity"}
            assert required.issubset(set(dr.keys())), f"Missing keys in {dr}"
            assert isinstance(dr["source"], str) and dr["source"], "source must be non-empty str"
            assert isinstance(dr["reason"], str) and dr["reason"], "reason must be non-empty str"
            assert dr["severity"] in ("warning", "error"), f"Invalid severity: {dr['severity']}"

    def test_degraded_reasons_not_lost_on_conversion(self) -> None:
        """Degraded reasons must survive to_dict → from_dict without data loss."""
        result = PredictionResult(
            home_team="France",
            away_team="Ivory Coast",
            competition="International Friendly",
            is_neutral=True,
            degraded_reasons=[
                DegradedReason(
                    source="market_calibration",
                    reason="api_unavailable",
                    severity="warning",
                    detail="No API key configured",
                ),
            ],
        )
        d = result.to_dict()
        restored = PredictionResult.from_dict(d)

        assert restored.home_team == "France"
        assert restored.away_team == "Ivory Coast"
        assert restored.is_neutral is True
        assert len(restored.degraded_reasons) == 1
        dr = restored.degraded_reasons[0]
        assert dr.source == "market_calibration"
        assert dr.reason == "api_unavailable"
        assert dr.detail == "No API key configured"

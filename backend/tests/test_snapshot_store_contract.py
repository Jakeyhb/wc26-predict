from __future__ import annotations

import pytest

from app.services.snapshot_store import _normalize_prediction_result, _require_match_id


def test_normalize_prediction_result_accepts_canonical_keys():
    result = {
        "meta": {"match_id": "12345678123456781234567812345678"},
        "prediction": {"top_scores": [{"score": "1-0", "prob": 0.12}]},
        "elo": {"elo_gap": 42.0, "detail": {"k_factor": 30.0}},
        "missing_inputs": ["weather"],
    }

    normalized = _normalize_prediction_result(result)

    assert normalized["prediction"]["top3_scores"] == [{"score": "1-0", "prob": 0.12}]
    assert normalized["elo"]["rating_gap"] == 42.0
    assert normalized["elo"]["k_factor"] == 30.0
    assert normalized["missing_inputs"] == ["weather"]


def test_normalize_prediction_result_accepts_legacy_missing_data():
    result = {
        "prediction": {"top3_scores": []},
        "elo": {"rating_gap": 0.0, "k_factor": 20.0},
        "missing_data": [{"item": "lineup"}, "odds"],
    }

    normalized = _normalize_prediction_result(result)

    assert normalized["missing_inputs"] == ["lineup", "odds"]


def test_require_match_id_rejects_empty_or_non_uuid_values():
    with pytest.raises(ValueError):
        _require_match_id("")
    with pytest.raises(ValueError):
        _require_match_id("not-a-match")


def test_require_match_id_accepts_dashed_and_compact_uuid_values():
    compact = "12345678123456781234567812345678"
    dashed = "12345678-1234-5678-1234-567812345678"
    assert _require_match_id(compact) == compact
    assert _require_match_id(dashed) == dashed

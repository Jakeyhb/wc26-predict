from __future__ import annotations

import json
import sqlite3

from scripts.backfill_evaluation_samples import run


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE prediction_snapshots (
            id TEXT PRIMARY KEY,
            match_id TEXT,
            generated_at TEXT,
            model_version TEXT,
            baseline_probs TEXT,
            adjusted_probs TEXT,
            component_probs TEXT,
            market_probs TEXT,
            pipeline_params TEXT
        );
        CREATE TABLE prediction_runs (
            id TEXT PRIMARY KEY,
            match_id TEXT,
            run_type TEXT,
            model_version TEXT,
            as_of_time TEXT,
            created_at TEXT,
            home_win_prob REAL,
            draw_prob REAL,
            away_win_prob REAL,
            input_feature_snapshot TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO prediction_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "snap1",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "2026-06-01T00:00:00",
            "legacy",
            json.dumps({"home": 0.4, "draw": 0.3, "away": 0.3}),
            json.dumps({"home": 0.5, "draw": 0.25, "away": 0.25}),
            json.dumps({"dc": {"home": 0.45, "draw": 0.30, "away": 0.25}}),
            json.dumps({"home": 0.42, "draw": 0.31, "away": 0.27}),
            "{}",
        ),
    )
    conn.execute(
        "INSERT INTO prediction_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "run1",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "MANUAL",
            "legacy",
            "2026-06-01T00:00:00",
            "2026-06-01T00:00:01",
            0.5,
            0.25,
            0.25,
            "{}",
        ),
    )
    return conn


def test_backfill_evaluation_samples_dry_run_does_not_write():
    conn = _make_db()

    result = run(conn, table="all", apply=False)

    assert result == {"prediction_snapshots_updated": 1, "prediction_runs_updated": 1}
    assert conn.execute("SELECT pipeline_params FROM prediction_snapshots").fetchone()[0] == "{}"
    assert conn.execute("SELECT input_feature_snapshot FROM prediction_runs").fetchone()[0] == "{}"


def test_backfill_evaluation_samples_apply_updates_same_row_json():
    conn = _make_db()

    result = run(conn, table="all", apply=True)

    assert result == {"prediction_snapshots_updated": 1, "prediction_runs_updated": 1}
    snapshot_params = json.loads(conn.execute("SELECT pipeline_params FROM prediction_snapshots").fetchone()[0])
    run_features = json.loads(conn.execute("SELECT input_feature_snapshot FROM prediction_runs").fetchone()[0])
    snapshot_sample = snapshot_params["evaluation_sample"]
    run_sample = run_features["evaluation_sample"]

    assert snapshot_sample["schema_version"] == "v1"
    assert snapshot_sample["candidate_probs"]["snapshot_adjusted"]["home"] == 0.5
    assert snapshot_sample["candidate_probs"]["dc_only"]["home"] == 0.45
    assert run_sample["candidate_probs"]["current_fusion"]["home"] == 0.5
    assert "dc_only" not in run_sample["candidate_probs"]

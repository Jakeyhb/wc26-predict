#!/usr/bin/env python3
"""Backfill V3.5.4 evaluation_sample JSON from same-row prediction data."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.evaluation_sample import UNIFORM_PROBS, build_evaluation_sample  # noqa: E402


DB_PATH = PROJECT_ROOT / "data" / "local_stage2.db"


def _json_obj(raw: object) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(str(raw))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _dump_json(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def _component_label(name: str) -> str:
    normalized = str(name).lower()
    return {
        "dc": "dc_only",
        "dixon_coles": "dc_only",
        "enhancer": "tabular_only",
        "tabular": "tabular_only",
        "elo": "elo_only",
        "pi": "pi_only",
        "pi_rating": "pi_only",
        "weibull": "weibull_only",
        "market": "market_only",
    }.get(normalized, f"component:{normalized}")


def _has_evaluation_sample(container: dict[str, Any]) -> bool:
    sample = container.get("evaluation_sample")
    return isinstance(sample, dict) and isinstance(sample.get("candidate_probs"), dict)


def build_snapshot_sample(row: sqlite3.Row) -> dict[str, Any]:
    baseline = _json_obj(row["baseline_probs"])
    adjusted = _json_obj(row["adjusted_probs"])
    market = _json_obj(row["market_probs"])
    raw_candidates: dict[str, Any] = {
        "current_fusion": adjusted,
        "snapshot_adjusted": adjusted,
        "snapshot_baseline": baseline,
        "market_only": market,
        "uniform_baseline": UNIFORM_PROBS,
    }
    for name, payload in _json_obj(row["component_probs"]).items():
        raw_candidates[_component_label(name)] = payload

    return build_evaluation_sample(
        match_id=str(row["match_id"] or ""),
        as_of_time=str(row["generated_at"] or ""),
        generated_at=str(row["generated_at"] or ""),
        model_version=str(row["model_version"] or ""),
        weight_label="legacy_snapshot_backfill",
        raw_candidates=raw_candidates,
    )


def build_prediction_run_sample(row: sqlite3.Row) -> dict[str, Any]:
    current = {
        "home": row["home_win_prob"],
        "draw": row["draw_prob"],
        "away": row["away_win_prob"],
    }
    return build_evaluation_sample(
        match_id=str(row["match_id"] or ""),
        as_of_time=str(row["as_of_time"] or ""),
        generated_at=str(row["created_at"] or row["as_of_time"] or ""),
        model_version=str(row["model_version"] or ""),
        weight_label="legacy_prediction_run_backfill",
        raw_candidates={
            "current_fusion": current,
            "uniform_baseline": UNIFORM_PROBS,
        },
    )


def _backup_db(db_path: Path) -> Path:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"local_stage2_pre_v354_eval_samples_{stamp}.db"
    shutil.copy2(db_path, backup_path)
    return backup_path


def _snapshot_updates(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    updates: list[tuple[str, str]] = []
    rows = conn.execute(
        """
        SELECT id, match_id, generated_at, model_version, baseline_probs, adjusted_probs,
               component_probs, market_probs, pipeline_params
        FROM prediction_snapshots
        WHERE match_id IS NOT NULL AND TRIM(match_id) <> ''
        """
    ).fetchall()
    for row in rows:
        pipeline_params = _json_obj(row["pipeline_params"])
        if _has_evaluation_sample(pipeline_params):
            continue
        pipeline_params["evaluation_sample"] = build_snapshot_sample(row)
        updates.append((row["id"], _dump_json(pipeline_params)))
    return updates


def _prediction_run_updates(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    updates: list[tuple[str, str]] = []
    rows = conn.execute(
        """
        SELECT id, match_id, run_type, model_version, as_of_time, created_at,
               home_win_prob, draw_prob, away_win_prob, input_feature_snapshot
        FROM prediction_runs
        WHERE match_id IS NOT NULL AND TRIM(CAST(match_id AS TEXT)) <> ''
        """
    ).fetchall()
    for row in rows:
        feature_snapshot = _json_obj(row["input_feature_snapshot"])
        if _has_evaluation_sample(feature_snapshot):
            continue
        feature_snapshot["evaluation_sample"] = build_prediction_run_sample(row)
        updates.append((row["id"], _dump_json(feature_snapshot)))
    return updates


def run(conn: sqlite3.Connection, *, table: str, apply: bool) -> dict[str, int]:
    result = {
        "prediction_snapshots_updated": 0,
        "prediction_runs_updated": 0,
    }
    if table in {"all", "prediction_snapshots"}:
        updates = _snapshot_updates(conn)
        result["prediction_snapshots_updated"] = len(updates)
        if apply and updates:
            conn.executemany(
                "UPDATE prediction_snapshots SET pipeline_params = ? WHERE id = ?",
                [(payload, row_id) for row_id, payload in updates],
            )
    if table in {"all", "prediction_runs"}:
        updates = _prediction_run_updates(conn)
        result["prediction_runs_updated"] = len(updates)
        if apply and updates:
            conn.executemany(
                "UPDATE prediction_runs SET input_feature_snapshot = ? WHERE id = ?",
                [(payload, row_id) for row_id, payload in updates],
            )
    if apply:
        conn.commit()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill V3.5.4 evaluation_sample JSON from same-row data.")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--table", choices=["all", "prediction_snapshots", "prediction_runs"], default="all")
    parser.add_argument("--apply", action="store_true", help="Apply updates. Default is dry-run.")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    backup_path = None
    if args.apply:
        backup_path = _backup_db(db_path)
        print(f"Backup: {backup_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        result = run(conn, table=args.table, apply=args.apply)
    finally:
        conn.close()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"Mode: {mode}")
    print(f"prediction_snapshots_updated={result['prediction_snapshots_updated']}")
    print(f"prediction_runs_updated={result['prediction_runs_updated']}")
    if not args.apply:
        print("No changes written. Re-run with --apply to update the database.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

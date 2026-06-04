#!/usr/bin/env python3
"""train_models.py — Offline training for all WC26 Predict models.

Trains ALL model components, saves artifacts to backend/artifacts/,
and writes the artifact registry at model_registry.json.

Usage:
    python scripts/train_models.py
    python scripts/train_models.py --team-type national --refresh
    python scripts/train_models.py --skip-weibull
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import sys
import time
from datetime import datetime, timezone
from multiprocessing import Process, Queue
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import joblib
import numpy as np
import pandas as pd
import sqlite3

from app.services.dixon_coles import DixonColesModel
from app.services.tabular_match_model import TabularMatchEnhancer
from app.services.elo_ratings import EloRatingSystem
from app.services.pi_ratings import PiRatingWrapper
from app.services.weibull_model import WeibullWrapper

# ── Paths ──
DB_PATH = BACKEND_DIR / "data" / "local_stage2.db"
ARTIFACTS_DIR = BACKEND_DIR / "artifacts"
DATAFRAMES_DIR = ARTIFACTS_DIR / "dataframes"
MODELS_DIR = ARTIFACTS_DIR / "models"
RATINGS_DIR = ARTIFACTS_DIR / "ratings"
REGISTRY_PATH = ARTIFACTS_DIR / "model_registry.json"


def _df_cache_path(team_type: str) -> Path:
    return DATAFRAMES_DIR / f"{team_type}_finished_matches.pkl"


# ═══════════════════════════════════════════════════════════════════════
#  1. Data loading
# ═══════════════════════════════════════════════════════════════════════

def load_training_data(team_type: str, refresh: bool = False) -> pd.DataFrame:
    """Load finished match data from SQLite (sync, no FastAPI async).

    Uses a cached pickle file for reuse.  Pass refresh=True to reload
    from SQLite and overwrite the cache.
    """
    DATAFRAMES_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _df_cache_path(team_type)

    if not refresh and cache_path.exists():
        print(f"  Loading cached dataframe from {cache_path}", flush=True)
        df = pd.read_pickle(cache_path)
        print(f"  Cached: {len(df)} matches, {df.home_team.nunique()} teams", flush=True)
        return df

    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    print(f"  Loading data from SQLite ({DB_PATH}) ...", flush=True)
    conn = sqlite3.connect(str(DB_PATH))

    team_filter = ""
    if team_type:
        team_filter = f"AND ht.team_type = '{team_type}' AND at.team_type = '{team_type}'"

    query = f"""
        SELECT ht.name AS home_team,
               at.name AS away_team,
               mr.home_goals,
               mr.away_goals,
               m.match_date,
               COALESCE(m.competition_weight, 1.0) AS competition_weight,
               COALESCE(m.is_neutral_venue, 0)     AS is_neutral_venue,
               m.competition,
               m.competition_type,
               m.stage,
               mr.home_xg,
               mr.away_xg
        FROM matches m
        JOIN teams ht ON m.home_team_id = ht.id
        JOIN teams at ON m.away_team_id = at.id
        JOIN match_results mr ON m.id = mr.match_id
        WHERE m.status = 'finished'
        {team_filter}
        ORDER BY m.match_date ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    df["match_date"] = pd.to_datetime(df["match_date"], utc=True, format="ISO8601")
    df.to_pickle(cache_path)
    print(f"  Loaded {len(df)} matches, {df.home_team.nunique()} teams", flush=True)
    return df


def compute_fingerprint(df: pd.DataFrame) -> str:
    """MD5 fingerprint of (row_count, max_match_date, team_count).

    Used to detect data drift between training runs.
    """
    row_count = len(df)
    max_date = str(df["match_date"].max()) if not df.empty else "none"
    team_count = int(df["home_team"].nunique()) if not df.empty else 0
    raw = f"{row_count}:{max_date}:{team_count}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


# ═══════════════════════════════════════════════════════════════════════
#  2. Individual model training helpers
# ═══════════════════════════════════════════════════════════════════════

def train_dixon_coles(df: pd.DataFrame) -> tuple[DixonColesModel, float]:
    """Fit Dixon-Coles on full dataframe.  Returns (model, fit_seconds)."""
    print("  [1/5] Training Dixon-Coles ...", end=" ", flush=True)
    t0 = time.perf_counter()
    dc = DixonColesModel()
    dc.fit(df)
    elapsed = time.perf_counter() - t0
    print(f"done  [{elapsed:.1f}s]", flush=True)
    return dc, elapsed


def train_enhancer(df: pd.DataFrame) -> tuple[TabularMatchEnhancer, float]:
    """Fit TabularMatchEnhancer on full dataframe.  Returns (model, fit_seconds)."""
    print("  [2/5] Training TabularMatchEnhancer ...", end=" ", flush=True)
    t0 = time.perf_counter()
    enh = TabularMatchEnhancer()
    enh.fit(df)
    elapsed = time.perf_counter() - t0
    print(f"done  [{elapsed:.1f}s]", flush=True)
    return enh, elapsed


def train_elo(df: pd.DataFrame) -> tuple[dict[str, float], float]:
    """Fit Elo rating system.  Returns (ratings_dict, fit_seconds)."""
    print("  [3/5] Training Elo ...", end=" ", flush=True)
    t0 = time.perf_counter()
    elo = EloRatingSystem()
    elo.fit(df)
    ratings = elo.get_ratings()
    elapsed = time.perf_counter() - t0
    print(f"done  [{elapsed:.1f}s]", flush=True)
    return ratings, elapsed


def train_pi(df: pd.DataFrame) -> tuple[dict[str, float], float]:
    """Fit Pi-Rating (penaltyblog).  Returns (ratings_dict, fit_seconds)."""
    print("  [4/5] Training Pi-Rating ...", end=" ", flush=True)
    t0 = time.perf_counter()
    pi = PiRatingWrapper()
    pi.fit(df)
    ratings = pi.get_ratings_dict()
    elapsed = time.perf_counter() - t0
    print(f"done  [{elapsed:.1f}s]", flush=True)
    return ratings, elapsed


# ── Weibull subprocess isolation ──

def _weibull_worker(df_path: str, output_path: str, result_queue: "Queue[str]") -> None:
    """Run inside a child process: fit Weibull, pickle on success, signal back."""
    try:
        df = pd.read_pickle(df_path)
        wb = WeibullWrapper()
        success = wb.fit(df)
        if success:
            with open(output_path, "wb") as f:
                pickle.dump(wb, f)
            result_queue.put("success")
        else:
            result_queue.put("failed:fit_returned_false")
    except Exception as exc:
        result_queue.put(f"failed:{exc}")


def train_weibull(df: pd.DataFrame) -> tuple[bool, float, str]:
    """Fit Weibull in a separate *process* with a 120-second timeout.

    Returns (success, elapsed_seconds, status_label) where status_label
    is ``"ready"``, ``"disabled_timeout"``, or ``"failed"``.
    """
    print("  [5/5] Training Weibull (subprocess, timeout=120s) ...", end=" ", flush=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # Use last 2000 matches (form-sensitive model)
    wb_df = df.sort_values("match_date").tail(2000).copy()
    temp_df_path = MODELS_DIR / "_weibull_temp_df.pkl"
    output_path = MODELS_DIR / "weibull.pkl"

    wb_df.to_pickle(temp_df_path)

    result_queue: Queue[str] = Queue()
    proc = Process(
        target=_weibull_worker,
        args=(str(temp_df_path), str(output_path), result_queue),
    )

    t0 = time.perf_counter()
    proc.start()
    proc.join(timeout=120)
    elapsed = time.perf_counter() - t0

    # Clean up temp file
    try:
        if temp_df_path.exists():
            temp_df_path.unlink()
    except Exception:
        pass

    if proc.is_alive():
        proc.terminate()
        proc.join()
        _try_remove(output_path)
        print(f"TIMEOUT  [{elapsed:.1f}s]", flush=True)
        return False, elapsed, "disabled_timeout"

    # --- Subprocess completed within the deadline ---
    try:
        result = result_queue.get_nowait()
    except Exception:
        result = "failed:no_result_from_subprocess"

    if result == "success":
        print(f"done  [{elapsed:.1f}s]", flush=True)
        return True, elapsed, "ready"

    # Failed — remove any artifact that was written
    _try_remove(output_path)
    print(f"FAILED  [{elapsed:.1f}s] ({result})", flush=True)
    return False, elapsed, "failed"


def _try_remove(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════
#  3. Artifact save helpers
# ═══════════════════════════════════════════════════════════════════════

def save_dc(dc: DixonColesModel) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with open(MODELS_DIR / "dc.pkl", "wb") as f:
        pickle.dump(dc, f)
    print(f"    -> {MODELS_DIR / 'dc.pkl'}", flush=True)


def save_enhancer(enh: TabularMatchEnhancer) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(enh, MODELS_DIR / "enhancer.joblib")
    print(f"    -> {MODELS_DIR / 'enhancer.joblib'}", flush=True)


def save_elo_ratings(ratings: dict[str, float]) -> None:
    RATINGS_DIR.mkdir(parents=True, exist_ok=True)
    path = RATINGS_DIR / "elo.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ratings, f, ensure_ascii=False, indent=2, sort_keys=True)
    print(f"    -> {path}  ({len(ratings)} teams)", flush=True)


def save_pi_ratings(ratings: dict[str, float]) -> None:
    RATINGS_DIR.mkdir(parents=True, exist_ok=True)
    path = RATINGS_DIR / "pi.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ratings, f, ensure_ascii=False, indent=2, sort_keys=True)
    print(f"    -> {path}  ({len(ratings)} teams)", flush=True)


# ═══════════════════════════════════════════════════════════════════════
#  4. Registry
# ═══════════════════════════════════════════════════════════════════════

def write_registry(registry: dict[str, Any]) -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)
    print(f"  Registry: {REGISTRY_PATH}", flush=True)


# ═══════════════════════════════════════════════════════════════════════
#  5. Main
# ═══════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="WC26 Predict — offline training for all models",
    )
    p.add_argument(
        "--team-type",
        default="national",
        help="Team type filter (default: national)",
    )
    p.add_argument(
        "--refresh",
        action="store_true",
        help="Force retrain even if cached dataframe exists",
    )
    p.add_argument(
        "--skip-weibull",
        action="store_true",
        help="Skip Weibull training entirely",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    print("=" * 60)
    print("  WC26 Predict — Offline Training")
    print(f"    Team type:       {args.team_type}")
    if args.refresh:
        print("    --refresh:       Force reload data from SQLite")
    if args.skip_weibull:
        print("    --skip-weibull:  Weibull will NOT be trained")
    print("=" * 60)
    print()

    # ── 1. Load data ────────────────────────────────────────────────
    print("[1] Loading training data")
    df = load_training_data(args.team_type, refresh=args.refresh)
    fingerprint = compute_fingerprint(df)
    training_rows = len(df)
    print(f"    Fingerprint:  {fingerprint}")
    print(f"    Rows:         {training_rows}")
    print(f"    Date range:   {df['match_date'].min().date()}  ->  {df['match_date'].max().date()}")
    print(f"    Teams:        {df.home_team.nunique()}")
    print()

    # Ensure all output directories exist
    for d in (ARTIFACTS_DIR, DATAFRAMES_DIR, MODELS_DIR, RATINGS_DIR):
        d.mkdir(parents=True, exist_ok=True)

    # ── 2. Train models ─────────────────────────────────────────────
    total_start = time.perf_counter()
    components: dict[str, dict[str, Any]] = {}

    # a. Dixon-Coles
    try:
        dc_model, dc_sec = train_dixon_coles(df)
        save_dc(dc_model)
        components["dixon_coles"] = {
            "status": "ready",
            "fit_seconds": round(dc_sec, 1),
            "required_for": ["full_pipeline", "baseline_pipeline"],
        }
    except Exception as exc:
        print(f"    ** FAILED: {exc}", flush=True)
        components["dixon_coles"] = {
            "status": "failed",
            "fit_seconds": 0,
            "required_for": ["full_pipeline", "baseline_pipeline"],
            "error": str(exc)[:200],
        }

    # b. TabularMatchEnhancer
    try:
        enh_model, enh_sec = train_enhancer(df)
        save_enhancer(enh_model)
        components["tabular_enhancer"] = {
            "status": "ready",
            "fit_seconds": round(enh_sec, 1),
            "required_for": ["full_pipeline"],
        }
    except Exception as exc:
        print(f"    ** FAILED: {exc}", flush=True)
        components["tabular_enhancer"] = {
            "status": "failed",
            "fit_seconds": 0,
            "required_for": ["full_pipeline"],
            "error": str(exc)[:200],
        }

    # c. Elo
    try:
        elo_ratings, elo_sec = train_elo(df)
        save_elo_ratings(elo_ratings)
        components["elo"] = {
            "status": "ready",
            "fit_seconds": round(elo_sec, 1),
            "required_for": ["full_pipeline"],
        }
    except Exception as exc:
        print(f"    ** FAILED: {exc}", flush=True)
        components["elo"] = {
            "status": "failed",
            "fit_seconds": 0,
            "required_for": ["full_pipeline"],
            "error": str(exc)[:200],
        }

    # d. Pi-Rating
    try:
        pi_ratings, pi_sec = train_pi(df)
        save_pi_ratings(pi_ratings)
        components["pi_rating"] = {
            "status": "ready",
            "fit_seconds": round(pi_sec, 1),
            "required_for": ["full_pipeline"],
        }
    except Exception as exc:
        print(f"    ** FAILED: {exc}", flush=True)
        components["pi_rating"] = {
            "status": "failed",
            "fit_seconds": 0,
            "required_for": ["full_pipeline"],
            "error": str(exc)[:200],
        }

    # e. Weibull (optional)
    if args.skip_weibull:
        print("  [5/5] Skipping Weibull (--skip-weibull)", flush=True)
        components["weibull"] = {
            "status": "skipped",
            "fit_seconds": 0,
            "required_for": ["full_pipeline"],
        }
    else:
        try:
            wb_ok, wb_sec, wb_status = train_weibull(df)
            components["weibull"] = {
                "status": wb_status,
                "fit_seconds": round(wb_sec, 1),
                "required_for": ["full_pipeline"],
            }
        except Exception as exc:
            print(f"    ** FAILED: {exc}", flush=True)
            components["weibull"] = {
                "status": "failed",
                "fit_seconds": 0,
                "required_for": ["full_pipeline"],
                "error": str(exc)[:200],
            }

    total_elapsed = time.perf_counter() - total_start

    # ── 3. Write registry ──────────────────────────────────────────
    registry: dict[str, Any] = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "data_fingerprint": fingerprint,
        "training_rows": training_rows,
        "team_type": args.team_type,
        "total_seconds": round(total_elapsed, 1),
        "components": components,
    }
    write_registry(registry)

    # ── 4. Print summary ────────────────────────────────────────────
    _print_summary(components, total_elapsed)


def _print_summary(components: dict[str, dict[str, Any]], total_elapsed: float) -> None:
    labels = {
        "dixon_coles": "Dixon-Coles",
        "tabular_enhancer": "TabularEnhancer",
        "elo": "Elo",
        "pi_rating": "Pi-Rating",
        "weibull": "Weibull",
    }

    print()
    print("TRAINING COMPLETE")
    for key, label in labels.items():
        info = components.get(key, {})
        status = info.get("status", "unknown")
        seconds = info.get("fit_seconds", 0)

        if status == "ready":
            status_fmt = "ready"
        elif status == "disabled_timeout":
            status_fmt = f"TIMEOUT (disabled)"
        elif status == "failed":
            err = info.get("error", "")
            status_fmt = f"FAILED  {err[:60]}"
        elif status == "skipped":
            status_fmt = "skipped"
        else:
            status_fmt = status

        status_fmt = status_fmt.replace("\\n", " ")
        print(f"  {label:<20} {seconds:>6.1f}s ({status_fmt})")

    print(f"  {'Total':<20} {total_elapsed:>6.1f}s")
    print(f"  Registry: {REGISTRY_PATH}")
    print()


if __name__ == "__main__":
    main()

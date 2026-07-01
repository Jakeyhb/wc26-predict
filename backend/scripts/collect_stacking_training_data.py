#!/usr/bin/env python3
"""collect_stacking_training_data.py — Walk-forward collection of all 7 component probs.

Generates (X, y) training pairs for the A3 Stacking Meta-Learner and calibration
records for the B1 Weighted Conformal Predictor by running a full walk-forward
backtest across all finished WC26 matches.

Methodology
-----------
For each unique match-date window (chronological):
  1. Train DC on all pre-window data (half_life=180d) → DC probs + xG
  2. Compute Elo ratings incrementally from pre-window history → Elo probs
  3. Compute Pi ratings incrementally from pre-window history → Pi probs
  4. Compute NegBin overdispersion-corrected probs from DC xG
  5. Fill Enhancer, Weibull, Market with uniform (⅓) — these require
     external features/API/training data not available in backtest
  6. Record all 7 component probabilities + actual result

Outputs
-------
- artifacts/stacking_training_data.json: (X, y) pairs + per-match details
- artifacts/conformal_calibration_records.json: B1 calibration set
- configs/stacking_backtest_results.json: comparative metrics

Usage:
    python scripts/collect_stacking_training_data.py
    python scripts/collect_stacking_training_data.py --skip-training  # only collect, don't train
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import numpy as np
import pandas as pd

from app.services.dixon_coles import DixonColesModel
from app.core.engine import (
    run_core_fusion,
    enforce_draw_floor,
    overdispersed_scoreline,
    CoreFusionResult,
    NEGBIN_R,
    NEGBIN_FUSION_WEIGHT,
)
from app.core.stacking_features import (
    assemble_feature_vector,
    encode_actual_result,
    STACKING_FEATURE_KEYS,
    STACKING_FEATURE_FILL,
    STACKING_C,
    STACKING_MAX_ITER,
    STACKING_MIN_TRAINING_SAMPLES,
)
from app.core.conformal_core import (
    nonconformity_score,
    CONFORMAL_ALPHA,
    CONFORMAL_MIN_CALIBRATION_SIZE,
)

# ── Paths ──
DB_PATH = BACKEND_DIR / "data" / "local_stage2.db"
ARTIFACTS_DIR = BACKEND_DIR / "artifacts"
CONFIG_DIR = BACKEND_DIR / "app" / "configs"
TRAINING_DATA_PATH = ARTIFACTS_DIR / "stacking_training_data.json"
CALIBRATION_PATH = ARTIFACTS_DIR / "conformal_calibration_records.json"
BACKTEST_OUTPUT_PATH = CONFIG_DIR / "stacking_backtest_results.json"
STACKING_MODEL_PATH = ARTIFACTS_DIR / "stacking_meta_learner.json"

# ── WC weights (V4.3.1) ──
WC_DC_WEIGHT = 0.90
WC_ENHANCER_WEIGHT = 0.10
WC_ELO_WEIGHT = 0.12
WC_PI_WEIGHT = 0.17

# ── Constants ──
WC26_COMPETITION = "FIFA World Cup 2026"
KO_STAGES = {
    "Round of 32", "Round of 16", "Quarter-finals",
    "Semi-finals", "Final", "Third Place",
}
DEFAULT_ELO = 1500.0
ELO_HOME_ADVANTAGE = 100.0
ELO_K_FACTOR = 32.0
DC_HALF_LIFE = 180  # confirmed optimal via grid search


# ═══════════════════════════════════════════════════════════════════════
#  Data loading (shared with backtest_full_pipeline.py)
# ═══════════════════════════════════════════════════════════════════════

def load_all_training_data(min_date: str = "2020-01-01") -> pd.DataFrame:
    """Load finished national-team matches from SQLite."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    conn = sqlite3.connect(str(DB_PATH))
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
               m.stage
        FROM matches m
        JOIN teams ht ON m.home_team_id = ht.id
        JOIN teams at ON m.away_team_id = at.id
        JOIN match_results mr ON m.id = mr.match_id
        WHERE m.status = 'finished'
          AND ht.team_type = 'national'
          AND at.team_type = 'national'
          AND m.match_date >= '{min_date}'
        ORDER BY m.match_date ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    df["match_date"] = pd.to_datetime(df["match_date"], utc=True, format="mixed")
    print(f"  Loaded {len(df):,} training matches, {df.home_team.nunique()} teams")
    return df


def load_wc26_eval_matches() -> pd.DataFrame:
    """Load WC26 matches that have results (evaluation targets)."""
    conn = sqlite3.connect(str(DB_PATH))
    query = """
        SELECT ht.name AS home_team,
               at.name AS away_team,
               mr.home_goals,
               mr.away_goals,
               m.match_date,
               COALESCE(m.is_neutral_venue, 1) AS is_neutral_venue,
               m.stage
        FROM matches m
        JOIN teams ht ON m.home_team_id = ht.id
        JOIN teams at ON m.away_team_id = at.id
        JOIN match_results mr ON m.id = mr.match_id
        WHERE m.competition = ?
        ORDER BY m.match_date ASC
    """
    df = pd.read_sql_query(query, conn, params=(WC26_COMPETITION,))
    conn.close()

    df["match_date"] = pd.to_datetime(df["match_date"], utc=True, format="mixed")
    group_count = sum(1 for s in df["stage"] if s not in KO_STAGES)
    ko_count = sum(1 for s in df["stage"] if s in KO_STAGES)
    print(f"  WC26 evaluation matches: {len(df)} ({group_count} group + {ko_count} KO)")
    return df


# ═══════════════════════════════════════════════════════════════════════
#  Elo computation (walk-forward, identical to backtest_full_pipeline.py)
# ═══════════════════════════════════════════════════════════════════════

def expected_score(r_home: float, r_away: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((r_away - r_home) / 400.0))


def elo_davidson_draw(gap: float, kappa: float = 0.30) -> float:
    r = gap / 400.0
    p_draw = kappa * math.sqrt(
        (1.0 / (1.0 + 10.0 ** (-r))) *
        (1.0 / (1.0 + 10.0 ** r))
    )
    return float(p_draw)


def compute_elo_probs(
    home_team: str, away_team: str,
    ratings: dict[str, float],
    is_neutral: bool = True,
    kappa: float = 0.30,
) -> dict[str, float]:
    r_home = ratings.get(home_team, DEFAULT_ELO)
    r_away = ratings.get(away_team, DEFAULT_ELO)
    home_adv = 0.0 if is_neutral else ELO_HOME_ADVANTAGE

    adj_home = r_home + home_adv
    gap = adj_home - r_away

    p_home_win = expected_score(adj_home, r_away)
    p_away_win = 1.0 - p_home_win
    p_draw = elo_davidson_draw(gap, kappa)

    remaining = 1.0 - p_draw
    if remaining > 0:
        p_home_win = p_home_win * remaining
        p_away_win = p_away_win * remaining

    total = p_home_win + p_draw + p_away_win
    if total > 0:
        p_home_win /= total
        p_draw /= total
        p_away_win /= total

    return {
        "home": float(p_home_win),
        "draw": float(p_draw),
        "away": float(p_away_win),
    }


def update_elo_ratings(
    ratings: dict[str, float],
    home_team: str, away_team: str,
    home_goals: int, away_goals: int,
    is_neutral: bool = True,
    k_factor: float = ELO_K_FACTOR,
) -> None:
    r_home = ratings.get(home_team, DEFAULT_ELO)
    r_away = ratings.get(away_team, DEFAULT_ELO)
    home_adv = 0.0 if is_neutral else ELO_HOME_ADVANTAGE

    adj_home = r_home + home_adv
    e_home = expected_score(adj_home, r_away)
    e_away = 1.0 - e_home

    if home_goals > away_goals:
        s_home, s_away = 1.0, 0.0
    elif home_goals == away_goals:
        s_home, s_away = 0.5, 0.5
    else:
        s_home, s_away = 0.0, 1.0

    goal_diff = abs(home_goals - away_goals)
    g_mult = 1.0
    if goal_diff == 2:
        g_mult = 1.5
    elif goal_diff >= 3:
        g_mult = 1.75

    ratings[home_team] = r_home + k_factor * g_mult * (s_home - e_home)
    ratings[away_team] = r_away + k_factor * g_mult * (s_away - e_away)


def build_elo_ratings_as_of(
    history_df: pd.DataFrame,
    cutoff_date: pd.Timestamp,
) -> dict[str, float]:
    ratings: dict[str, float] = {}
    pre_df = history_df[history_df["match_date"] < cutoff_date]
    for row in pre_df.itertuples(index=False):
        update_elo_ratings(
            ratings,
            row.home_team, row.away_team,
            int(row.home_goals), int(row.away_goals),
            is_neutral=bool(row.is_neutral_venue),
        )
    return ratings


# ═══════════════════════════════════════════════════════════════════════
#  Pi-Rating computation (walk-forward)
# ═══════════════════════════════════════════════════════════════════════

def compute_pi_probs(
    home_team: str, away_team: str,
    pi_ratings: dict[str, float],
    is_neutral: bool = True,
) -> dict[str, float]:
    r_home = pi_ratings.get(home_team, 0.0)
    r_away = pi_ratings.get(away_team, 0.0)

    home_adj = 0.0 if is_neutral else 0.3
    xg_diff = (r_home + home_adj - r_away) * 0.35

    p_home_win = 1.0 / (1.0 + math.exp(-xg_diff * 2.5))
    p_away_win = 1.0 / (1.0 + math.exp(xg_diff * 2.5))
    p_draw = 0.26 * math.exp(-xg_diff * xg_diff / 2.0)

    total = p_home_win + p_draw + p_away_win
    if total > 0:
        p_home_win /= total
        p_draw /= total
        p_away_win /= total

    return {
        "home": float(p_home_win),
        "draw": float(p_draw),
        "away": float(p_away_win),
    }


def update_pi_ratings(
    pi_ratings: dict[str, float],
    home_team: str, away_team: str,
    home_goals: int, away_goals: int,
    is_neutral: bool = True,
    k: float = 0.1,
) -> None:
    r_home = pi_ratings.get(home_team, 0.0)
    r_away = pi_ratings.get(away_team, 0.0)
    home_adj = 0.0 if is_neutral else 0.3

    xg_diff = (r_home + home_adj - r_away) * 0.35
    e_home = 1.0 / (1.0 + math.exp(-xg_diff * 2.5))
    e_away = 1.0 - e_home

    if home_goals > away_goals:
        s_home, s_away = 1.0, 0.0
    elif home_goals == away_goals:
        s_home, s_away = 0.5, 0.5
    else:
        s_home, s_away = 0.0, 1.0

    goal_diff = abs(home_goals - away_goals)
    g_mult = min(2.0, 1.0 + goal_diff * 0.25)

    pi_ratings[home_team] = r_home + k * g_mult * (s_home - e_home)
    pi_ratings[away_team] = r_away + k * g_mult * (s_away - e_away)


def build_pi_ratings_as_of(
    history_df: pd.DataFrame,
    cutoff_date: pd.Timestamp,
) -> dict[str, float]:
    pi_ratings: dict[str, float] = {}
    pre_df = history_df[history_df["match_date"] < cutoff_date]
    for row in pre_df.itertuples(index=False):
        update_pi_ratings(
            pi_ratings,
            row.home_team, row.away_team,
            int(row.home_goals), int(row.away_goals),
            is_neutral=bool(row.is_neutral_venue),
        )
    return pi_ratings


# ═══════════════════════════════════════════════════════════════════════
#  NegBin component (from engine.py)
# ═══════════════════════════════════════════════════════════════════════

def compute_negbin_probs(home_xg: float, away_xg: float) -> dict[str, float]:
    """Compute NegBin overdispersion-corrected H/D/A probabilities."""
    if home_xg <= 0 or away_xg <= 0:
        return {"home": STACKING_FEATURE_FILL, "draw": STACKING_FEATURE_FILL,
                "away": STACKING_FEATURE_FILL}
    try:
        od = overdispersed_scoreline(home_xg, away_xg)
        nb = od["negbin"]
        total = nb["home_win"] + nb["draw"] + nb["away_win"]
        if total <= 0:
            return {"home": STACKING_FEATURE_FILL, "draw": STACKING_FEATURE_FILL,
                    "away": STACKING_FEATURE_FILL}
        return {
            "home": nb["home_win"] / total,
            "draw": nb["draw"] / total,
            "away": nb["away_win"] / total,
        }
    except Exception:
        return {"home": STACKING_FEATURE_FILL, "draw": STACKING_FEATURE_FILL,
                "away": STACKING_FEATURE_FILL}


# ═══════════════════════════════════════════════════════════════════════
#  Evaluation helpers
# ═══════════════════════════════════════════════════════════════════════

def determine_actual(home_goals: int, away_goals: int) -> tuple[int, str]:
    """Return (index, label) for actual outcome.  0=H, 1=D, 2=A."""
    if home_goals > away_goals:
        return 0, "H"
    elif home_goals == away_goals:
        return 1, "D"
    return 2, "A"


def _resolve_triplet(probs: dict[str, float]) -> list[float]:
    """Resolve H/D/A probabilities from either short or long key convention.

    Returns [P(home), P(draw), P(away)].
    """
    # Try short keys first, then long keys
    h = float(probs.get("home", probs.get("home_win_prob", probs.get("home_win", 1/3))))
    d = float(probs.get("draw", probs.get("draw_prob", 1/3)))
    a = float(probs.get("away", probs.get("away_win_prob", probs.get("away_win", 1/3))))
    return [h, d, a]


def compute_brier(probs: dict[str, float], actual_idx: int) -> float:
    prob_vec = np.array(_resolve_triplet(probs), dtype=float)
    actual = np.zeros(3)
    actual[actual_idx] = 1.0
    return float(((prob_vec - actual) ** 2).sum())


def compute_direction(probs: dict[str, float]) -> int:
    return int(np.argmax(_resolve_triplet(probs)))


# ═══════════════════════════════════════════════════════════════════════
#  Main collection loop
# ═══════════════════════════════════════════════════════════════════════

def collect_training_data(
    train_df: pd.DataFrame,
    eval_df: pd.DataFrame,
    half_life: int = DC_HALF_LIFE,
) -> dict[str, Any]:
    """Walk-forward collection of all 7 component probs for every WC26 match.

    Returns:
        Dict with:
          - X: list of 21-feature vectors
          - y: list of int labels (0=H, 1=D, 2=A)
          - calibration_records: list of dicts for B1
          - per_match: list of per-match detail dicts
          - metrics: aggregated metrics
    """
    unique_dates = sorted(eval_df["match_date"].dt.normalize().unique())
    n_windows = len(unique_dates)
    print(f"  Walk-forward over {n_windows} unique dates")
    print()

    # Storage
    X: list[list[float]] = []          # 21-element feature vectors
    y: list[int] = []                  # 0=H, 1=D, 2=A
    calibration_records: list[dict] = []   # for B1
    per_match: list[dict] = []

    # Metrics tracking
    dc_briers: list[float] = []
    dc_dirs: list[int] = []
    sequential_briers: list[float] = []
    sequential_dirs: list[int] = []
    n_draws = 0

    total_dc_fit_time = 0.0

    # ── Window-by-window ──
    for win_idx, date_val in enumerate(unique_dates):
        day_matches = eval_df[eval_df["match_date"].dt.normalize() == date_val]
        n_day = len(day_matches)

        # Build Elo/Pi ratings from pre-window history
        elo_ratings = build_elo_ratings_as_of(train_df, date_val)
        pi_ratings = build_pi_ratings_as_of(train_df, date_val)

        # Train DC on pre-window data
        train_cut = train_df[train_df["match_date"].dt.normalize() < date_val]
        if len(train_cut) < 100:
            print(f"    WARN {date_val.date()}: only {len(train_cut)} training rows, skipping")
            continue

        t_fit = time.perf_counter()
        model = DixonColesModel(half_life_days=half_life)
        model.fit(train_cut)
        dc_fit_time = time.perf_counter() - t_fit
        total_dc_fit_time += dc_fit_time

        # ── Evaluate each match on this date ──
        for match_row in day_matches.itertuples(index=False):
            home_team = match_row.home_team
            away_team = match_row.away_team
            is_neutral = bool(match_row.is_neutral_venue)
            stage = match_row.stage
            home_goals = int(match_row.home_goals)
            away_goals = int(match_row.away_goals)
            match_date_str = str(match_row.match_date.date())
            actual_idx, actual_label = determine_actual(home_goals, away_goals)

            is_ko = stage in KO_STAGES
            kappa = 0.30

            # ── 1. DC probs ──
            dc_pred = model.predict_match(home_team, away_team, is_neutral_venue=is_neutral)
            dc_home = float(dc_pred["home_win_prob"])
            dc_draw = float(dc_pred["draw_prob"])
            dc_away = float(dc_pred["away_win_prob"])
            dc_xg_home = float(dc_pred.get("home_xg", 1.0))
            dc_xg_away = float(dc_pred.get("away_xg", 1.0))
            dc_probs = {"home": dc_home, "draw": dc_draw, "away": dc_away}

            # ── 2. Elo probs ──
            elo_probs = compute_elo_probs(home_team, away_team, elo_ratings, is_neutral, kappa)

            # ── 3. Pi probs ──
            pi_probs = compute_pi_probs(home_team, away_team, pi_ratings, is_neutral)

            # ── 4. NegBin probs ──
            negbin_probs = compute_negbin_probs(dc_xg_home, dc_xg_away)

            # ── 5-7. Fill uniform: Enhancer, Weibull, Market ──
            enhancer_probs = {"home": 1/3, "draw": 1/3, "away": 1/3}
            weibull_probs = {"home": 1/3, "draw": 1/3, "away": 1/3}
            market_probs = {"home": 1/3, "draw": 1/3, "away": 1/3}

            # ── Build component_probs dict for stacking ──
            component_probs = {
                "dixon_coles": dc_probs,
                "enhancer": enhancer_probs,
                "negbin": negbin_probs,
                "weibull": weibull_probs,
                "elo": elo_probs,
                "pi_rating": pi_probs,
                "market": market_probs,
            }

            # ── Assemble feature vector ──
            feat = assemble_feature_vector(component_probs, market_probs)
            assert len(feat) == 21, f"Expected 21 features, got {len(feat)}"

            # ── Sequential fusion (for comparison baseline) ──
            fusion_result = run_core_fusion(
                dc_probs={
                    "home_win_prob": dc_home, "draw_prob": dc_draw, "away_win_prob": dc_away,
                },
                dc_home_xg=dc_xg_home,
                dc_away_xg=dc_xg_away,
                dc_base_weight=WC_DC_WEIGHT,
                enh_probs=None,      # Skip Enhancer (23% accuracy, noise floor)
                weibull_probs=None,  # Skip Weibull (30% failure rate)
                weibull_weight=0.0,
                elo_probs={
                    "home_win_prob": elo_probs["home"], "draw_prob": elo_probs["draw"],
                    "away_win_prob": elo_probs["away"],
                },
                elo_weight=WC_ELO_WEIGHT,
                pi_probs={
                    "home_win_prob": pi_probs["home"], "draw_prob": pi_probs["draw"],
                    "away_win_prob": pi_probs["away"],
                },
                pi_weight=WC_PI_WEIGHT,
            )
            fused_after_floor, _ = enforce_draw_floor(dict(fusion_result.probs))

            # ── Metrics ──
            dc_brier = compute_brier(dc_probs, actual_idx)
            seq_brier = compute_brier(fused_after_floor, actual_idx)
            dc_dir = compute_direction(dc_probs)
            seq_dir = compute_direction(fused_after_floor)

            dc_briers.append(dc_brier)
            dc_dirs.append(1 if dc_dir == actual_idx else 0)
            sequential_briers.append(seq_brier)
            sequential_dirs.append(1 if seq_dir == actual_idx else 0)
            if actual_idx == 1:
                n_draws += 1

            # ── Record (X, y) pair ──
            X.append(feat)
            y.append(actual_idx)

            # ── Calibration record for B1 ──
            calibration_records.append({
                "home_win_prob": fused_after_floor.get("home_win_prob", 1/3),
                "draw_prob": fused_after_floor.get("draw_prob", 1/3),
                "away_win_prob": fused_after_floor.get("away_win_prob", 1/3),
                "actual_result": actual_label,
                "match_date": match_date_str,
            })

            # ── Per-match detail ──
            per_match.append({
                "match": f"{home_team} vs {away_team}",
                "date": match_date_str,
                "stage": stage,
                "is_ko": is_ko,
                "actual": f"{home_goals}-{away_goals}",
                "actual_label": actual_label,
                "actual_idx": actual_idx,
                "dc_probs": {k: round(v, 4) for k, v in dc_probs.items()},
                "elo_probs": {k: round(v, 4) for k, v in elo_probs.items()},
                "pi_probs": {k: round(v, 4) for k, v in pi_probs.items()},
                "negbin_probs": {k: round(v, 4) for k, v in negbin_probs.items()},
                "sequential_probs": {
                    "home": round(fused_after_floor.get("home_win_prob", 0), 4),
                    "draw": round(fused_after_floor.get("draw_prob", 0), 4),
                    "away": round(fused_after_floor.get("away_win_prob", 0), 4),
                },
                "dc_brier": round(dc_brier, 6),
                "sequential_brier": round(seq_brier, 6),
                "dc_direction": "correct" if dc_dir == actual_idx else "wrong",
                "sequential_direction": "correct" if seq_dir == actual_idx else "wrong",
                "feature_vector": [round(v, 4) for v in feat],
            })

        # ── Progress ──
        day_dir = sum(
            1 for d in per_match[-n_day:]
            if d["sequential_direction"] == "correct"
        ) if n_day > 0 else 0
        bar = "#" if day_dir >= n_day / 2 else "."
        print(
            f"    [{win_idx+1}/{n_windows}] {date_val.date()}  {n_day} matches  "
            f"Dir={day_dir}/{n_day}  DC_fit={dc_fit_time:.1f}s  {bar}",
            flush=True,
        )

    # ── Aggregate metrics ──
    n_total = len(per_match)
    metrics = {
        "n_matches": n_total,
        "n_draws": n_draws,
        "draw_rate": n_draws / n_total if n_total > 0 else 0,
        "dc_brier_mean": float(np.mean(dc_briers)) if dc_briers else None,
        "sequential_brier_mean": float(np.mean(sequential_briers)) if sequential_briers else None,
        "dc_direction_accuracy": sum(dc_dirs) / n_total if n_total > 0 else None,
        "sequential_direction_accuracy": sum(sequential_dirs) / n_total if n_total > 0 else None,
        "n_training_pairs": len(X),
        "n_calibration_records": len(calibration_records),
        "total_dc_fit_time_s": round(total_dc_fit_time, 1),
    }

    # By-stage breakdown
    group_matches = [d for d in per_match if not d["is_ko"]]
    ko_matches = [d for d in per_match if d["is_ko"]]
    if group_matches:
        g_brier = np.mean([d["sequential_brier"] for d in group_matches])
        g_dir = sum(1 for d in group_matches if d["sequential_direction"] == "correct") / len(group_matches)
        metrics["group_stage"] = {"n": len(group_matches), "brier": float(g_brier), "direction": float(g_dir)}
    if ko_matches:
        k_brier = np.mean([d["sequential_brier"] for d in ko_matches])
        k_dir = sum(1 for d in ko_matches if d["sequential_direction"] == "correct") / len(ko_matches)
        metrics["knockout"] = {"n": len(ko_matches), "brier": float(k_brier), "direction": float(k_dir)}

    return {
        "X": X,
        "y": y,
        "calibration_records": calibration_records,
        "per_match": per_match,
        "metrics": metrics,
    }


# ═══════════════════════════════════════════════════════════════════════
#  A3 Training (TimeSeriesSplit)
# ═══════════════════════════════════════════════════════════════════════

def train_and_validate_stacking(
    X: list[list[float]],
    y: list[int],
    per_match: list[dict],
) -> dict[str, Any]:
    """Train A3 StackingMetaLearner with TimeSeriesSplit validation.

    The data is already in chronological order (walk-forward collection).
    We use expanding-window TimeSeriesSplit: train on first k matches,
    validate on match k+1...m, repeat.
    """
    n = len(X)
    if n < STACKING_MIN_TRAINING_SAMPLES * 2:
        print(f"  WARNING: Only {n} training samples — insufficient for TimeSeriesSplit "
              f"(need ≥{STACKING_MIN_TRAINING_SAMPLES * 2})")
        return {
            "trained": False,
            "reason": f"insufficient_samples ({n} < {STACKING_MIN_TRAINING_SAMPLES * 2})",
            "n_samples": n,
        }

    try:
        from sklearn.model_selection import TimeSeriesSplit
        from sklearn.linear_model import LogisticRegression
        SKLEARN_AVAILABLE = True
    except ImportError:
        SKLEARN_AVAILABLE = False
        print("  WARNING: sklearn not available — skipping A3 training")
        return {"trained": False, "reason": "sklearn_unavailable", "n_samples": n}

    X_np = np.array(X, dtype=float)
    y_np = np.array(y, dtype=int)

    # Use ~30% of data for initial training, with at least 20 samples
    min_train = max(STACKING_MIN_TRAINING_SAMPLES, int(n * 0.3))
    n_splits = max(3, min(10, (n - min_train) // 5))

    tscv = TimeSeriesSplit(n_splits=n_splits, test_size=None, gap=0)

    # We need to respect chronological order while maximizing training data.
    # TimeSeriesSplit naturally does expanding-window.
    # Minimum train size:
    tscv = TimeSeriesSplit(n_splits=n_splits)

    fold_results: list[dict] = []
    all_val_briers: list[float] = []
    all_val_y: list[int] = []
    all_val_stacking_preds: list[list[float]] = []
    all_val_seq_preds: list[list[float]] = []

    for fold_idx, (train_idx, val_idx) in enumerate(tscv.split(X_np)):
        X_train_fold = X_np[train_idx]
        y_train_fold = y_np[train_idx]
        X_val_fold = X_np[val_idx]
        y_val_fold = y_np[val_idx]

        if len(X_train_fold) < STACKING_MIN_TRAINING_SAMPLES:
            continue

        # Train stacking model (sklearn >=1.5 removed multi_class param)
        try:
            model = LogisticRegression(
                multi_class="multinomial", solver="lbfgs",
                C=STACKING_C, max_iter=STACKING_MAX_ITER, random_state=42,
            )
        except TypeError:
            model = LogisticRegression(
                solver="lbfgs", C=STACKING_C, max_iter=STACKING_MAX_ITER,
                random_state=42,
            )
        model.fit(X_train_fold, y_train_fold)

        # Predict
        stacking_preds = model.predict_proba(X_val_fold)  # (n_val, 3)

        # Get sequential fusion predictions for comparison
        seq_preds = []
        val_details = [per_match[i] for i in val_idx]
        for d in val_details:
            sp = d["sequential_probs"]
            seq_preds.append([sp["home"], sp["draw"], sp["away"]])
        seq_preds_np = np.array(seq_preds, dtype=float)

        # Brier scores
        fold_stacking_briers = []
        fold_seq_briers = []
        fold_stacking_dir_correct = 0
        fold_seq_dir_correct = 0

        for j, actual in enumerate(y_val_fold):
            actual_vec = np.zeros(3)
            actual_vec[actual] = 1.0

            s_brier = float(((stacking_preds[j] - actual_vec) ** 2).sum())
            q_brier = float(((seq_preds_np[j] - actual_vec) ** 2).sum())

            fold_stacking_briers.append(s_brier)
            fold_seq_briers.append(q_brier)

            s_dir = int(np.argmax(stacking_preds[j]))
            q_dir = int(np.argmax(seq_preds_np[j]))
            if s_dir == actual:
                fold_stacking_dir_correct += 1
            if q_dir == actual:
                fold_seq_dir_correct += 1

            # Collect for global ECE
            all_val_briers.append(s_brier)
            all_val_y.append(actual)
            all_val_stacking_preds.append(stacking_preds[j].tolist())
            all_val_seq_preds.append(seq_preds_np[j].tolist())

        n_val = len(val_idx)
        fold_results.append({
            "fold": fold_idx + 1,
            "train_size": len(train_idx),
            "val_size": n_val,
            "stacking_brier": float(np.mean(fold_stacking_briers)),
            "sequential_brier": float(np.mean(fold_seq_briers)),
            "stacking_direction": fold_stacking_dir_correct / n_val,
            "sequential_direction": fold_seq_dir_correct / n_val,
        })

        print(
            f"    Fold {fold_idx+1}: train={len(train_idx)} val={n_val}  "
            f"Stacking_Brier={np.mean(fold_stacking_briers):.4f}  "
            f"Seq_Brier={np.mean(fold_seq_briers):.4f}  "
            f"Stacking_Dir={fold_stacking_dir_correct/n_val:.1%}  "
            f"Seq_Dir={fold_seq_dir_correct/n_val:.1%}",
            flush=True,
        )

    if not fold_results:
        return {"trained": False, "reason": "no_valid_folds", "n_samples": n}

    # ── Train final model on ALL data ──
    try:
        final_model = LogisticRegression(
            multi_class="multinomial", solver="lbfgs",
            C=STACKING_C, max_iter=STACKING_MAX_ITER, random_state=42,
        )
    except TypeError:
        final_model = LogisticRegression(
            solver="lbfgs", C=STACKING_C, max_iter=STACKING_MAX_ITER, random_state=42,
        )
    final_model.fit(X_np, y_np)

    # ── Aggregate ──
    mean_stacking_brier = float(np.mean([f["stacking_brier"] for f in fold_results]))
    mean_seq_brier = float(np.mean([f["sequential_brier"] for f in fold_results]))
    mean_stacking_dir = float(np.mean([f["stacking_direction"] for f in fold_results]))
    mean_seq_dir = float(np.mean([f["sequential_direction"] for f in fold_results]))

    return {
        "trained": True,
        "n_samples": n,
        "n_folds": len(fold_results),
        "cv_stacking_brier_mean": round(mean_stacking_brier, 6),
        "cv_sequential_brier_mean": round(mean_seq_brier, 6),
        "cv_stacking_direction_mean": round(mean_stacking_dir, 4),
        "cv_sequential_direction_mean": round(mean_seq_dir, 4),
        "stacking_better": mean_stacking_brier < mean_seq_brier,
        "brier_delta": round(mean_stacking_brier - mean_seq_brier, 6),
        "fold_details": fold_results,
        "coefficients": final_model.coef_.tolist(),
        "intercept": final_model.intercept_.tolist(),
        "classes": [int(c) for c in final_model.classes_],
        "n_features": final_model.n_features_in_,
    }


# ═══════════════════════════════════════════════════════════════════════
#  Save artifacts
# ═══════════════════════════════════════════════════════════════════════

def save_training_data(data: dict[str, Any]) -> None:
    """Save collected (X, y) pairs + per-match details."""
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "description": "Walk-forward collected stacking training data for A3 meta-learner",
        "dc_half_life": DC_HALF_LIFE,
        "n_samples": len(data["X"]),
        "n_features": len(data["X"][0]) if data["X"] else 0,
        "n_calibration_records": len(data["calibration_records"]),
        "metrics": data["metrics"],
        "X": data["X"],
        "y": data["y"],
        "per_match": data["per_match"],
    }
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    TRAINING_DATA_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n  Training data saved to: {TRAINING_DATA_PATH}")


def save_calibration_records(records: list[dict]) -> None:
    """Save calibration records for B1 WeightedConformalPredictor."""
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "description": "Calibration records for B1 Weighted Conformal Predictor",
        "alpha": CONFORMAL_ALPHA,
        "n_records": len(records),
        "calibration_records": records,
    }
    CALIBRATION_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  Calibration records saved to: {CALIBRATION_PATH}")


def save_stacking_model(cv_result: dict[str, Any]) -> None:
    """Save trained A3 StackingMetaLearner coefficients as JSON."""
    if not cv_result.get("trained"):
        print(f"  Skipping model save — not trained: {cv_result.get('reason')}")
        return

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "description": "A3 Stacking Meta-Learner trained on 54 WC26 matches (walk-forward)",
        "coef": cv_result["coefficients"],
        "intercept": cv_result["intercept"],
        "classes": cv_result["classes"],
        "feature_names": list(STACKING_FEATURE_KEYS),
        "is_fitted": True,
        "fitted_at": datetime.now(timezone.utc).isoformat(),
        "training_sample_count": cv_result["n_samples"],
        "C": STACKING_C,
        "max_iter": STACKING_MAX_ITER,
        "cv_stacking_brier_mean": cv_result["cv_stacking_brier_mean"],
        "cv_sequential_brier_mean": cv_result["cv_sequential_brier_mean"],
    }
    STACKING_MODEL_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  Stacking model saved to: {STACKING_MODEL_PATH}")


def save_backtest_results(
    data: dict[str, Any],
    cv_result: dict[str, Any],
) -> None:
    """Save full backtest + CV results for auditing."""
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dc_half_life": DC_HALF_LIFE,
        "metrics": data["metrics"],
        "cv_validation": {
            "trained": cv_result.get("trained"),
            "n_folds": cv_result.get("n_folds"),
            "cv_stacking_brier_mean": cv_result.get("cv_stacking_brier_mean"),
            "cv_sequential_brier_mean": cv_result.get("cv_sequential_brier_mean"),
            "cv_stacking_direction_mean": cv_result.get("cv_stacking_direction_mean"),
            "cv_sequential_direction_mean": cv_result.get("cv_sequential_direction_mean"),
            "stacking_better": cv_result.get("stacking_better"),
            "brier_delta": cv_result.get("brier_delta"),
            "fold_details": cv_result.get("fold_details"),
        },
    }
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    BACKTEST_OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  Backtest results saved to: {BACKTEST_OUTPUT_PATH}")


# ═══════════════════════════════════════════════════════════════════════
#  Report
# ═══════════════════════════════════════════════════════════════════════

def print_summary(data: dict[str, Any], cv_result: dict[str, Any]) -> None:
    """Print comprehensive summary of the data collection and training."""
    metrics = data["metrics"]
    print(f"\n{'='*80}")
    print(f"  STACKING TRAINING DATA COLLECTION — SUMMARY")
    print(f"{'='*80}")
    print(f"  DC half-life: {DC_HALF_LIFE}d")
    print(f"  WC26 matches processed: {metrics['n_matches']}")
    print(f"  Training pairs (X,y): {len(data['X'])}")
    print(f"  Calibration records: {len(data['calibration_records'])}")
    print(f"  Features per sample: {len(data['X'][0]) if data['X'] else 0}")
    print()
    print(f"  ── Sequential Fusion Baseline ──")
    print(f"  DC Brier:             {metrics['dc_brier_mean']:.4f}")
    print(f"  Sequential Brier:     {metrics['sequential_brier_mean']:.4f}")
    print(f"  DC Dir Accuracy:      {metrics['dc_direction_accuracy']:.1%}")
    print(f"  Sequential Dir Acc:   {metrics['sequential_direction_accuracy']:.1%}")
    print(f"  Draw rate (actual):   {metrics['draw_rate']:.1%} ({metrics['n_draws']}/{metrics['n_matches']})")

    if metrics.get("group_stage"):
        gs = metrics["group_stage"]
        print(f"\n  ── Group Stage ({gs['n']} matches) ──")
        print(f"  Sequential Brier:     {gs['brier']:.4f}")
        print(f"  Sequential Dir:       {gs['direction']:.1%}")
    if metrics.get("knockout"):
        ko = metrics["knockout"]
        print(f"\n  ── Knockout ({ko['n']} matches) ──")
        print(f"  Sequential Brier:     {ko['brier']:.4f}")
        print(f"  Sequential Dir:       {ko['direction']:.1%}")

    if cv_result.get("trained"):
        print(f"\n  ── A3 Stacking CV ({cv_result['n_folds']} folds) ──")
        print(f"  Stacking Brier mean:  {cv_result['cv_stacking_brier_mean']:.4f}")
        print(f"  Sequential Brier mean:{cv_result['cv_sequential_brier_mean']:.4f}")
        print(f"  Stacking Dir mean:    {cv_result['cv_stacking_direction_mean']:.1%}")
        print(f"  Sequential Dir mean:  {cv_result['cv_sequential_direction_mean']:.1%}")
        delta = cv_result['brier_delta']
        better = "BETTER" if cv_result['stacking_better'] else "WORSE"
        print(f"  ΔBrier (Stacking-Seq): {'+' if delta > 0 else ''}{delta:.6f} — Stacking is {better}")
        print()
        if cv_result['stacking_better']:
            print(f"  [PASS] A3 Stacking outperforms sequential fusion on walk-forward CV!")
        else:
            print(f"  [INFO] A3 Stacking does NOT beat sequential fusion yet.")
            print(f"     - Consider: more components (Enhancer/Weibull real probs)")
            print(f"     - Or: more matches needed for meta-learner training")
    else:
        print(f"\n  ── A3 Stacking Training ──")
        print(f"  Not trained: {cv_result.get('reason', 'unknown')}")

    print(f"\n{'='*80}")

    # Per-component fill rates (how many matches had real vs uniform-filled probs)
    n_filled = sum(1 for d in data["per_match"] if d["negbin_probs"]["home"] != 1/3)
    print(f"\n  Component data availability (non-uniform):")
    print(f"    DC:     {metrics['n_matches']}/{metrics['n_matches']} (100%)")
    print(f"    Elo:    {metrics['n_matches']}/{metrics['n_matches']} (100%)")
    print(f"    Pi:     {metrics['n_matches']}/{metrics['n_matches']} (100%)")
    print(f"    NegBin: {n_filled}/{metrics['n_matches']} ({n_filled/metrics['n_matches']:.0%})")
    print(f"    Enhancer/Weibull/Market: 0/{metrics['n_matches']} (uniform-filled)")
    print()


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect stacking training data via walk-forward backtest",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--skip-training",
        action="store_true",
        help="Only collect training data, skip A3 model training",
    )
    parser.add_argument(
        "--halflife",
        type=int,
        default=DC_HALF_LIFE,
        help=f"DC half-life in days (default: {DC_HALF_LIFE})",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("  STACKING TRAINING DATA COLLECTION")
    print("  Walk-forward backtest with all 7 component probabilities")
    print("=" * 80)
    print(f"  DC half-life: {args.halflife}d")
    print()

    # ── Load data ──
    print("-- Loading data --")
    train_df = load_all_training_data()
    eval_df = load_wc26_eval_matches()

    # ── Collect ──
    print(f"\n-- Collecting component probs (walk-forward) --")
    t0 = time.perf_counter()
    data = collect_training_data(train_df, eval_df, half_life=args.halflife)
    elapsed = time.perf_counter() - t0

    print(f"\n  Collection complete in {elapsed:.1f}s")
    print(f"  Collected {len(data['X'])} training samples, "
          f"{len(data['calibration_records'])} calibration records")

    # ── Train A3 ──
    cv_result: dict[str, Any] = {"trained": False, "reason": "skipped"}
    if not args.skip_training:
        print(f"\n-- Training A3 Stacking Meta-Learner (TimeSeriesSplit CV) --")
        cv_result = train_and_validate_stacking(data["X"], data["y"], data["per_match"])

    # ── Save ──
    print(f"\n-- Saving artifacts --")
    save_training_data(data)
    save_calibration_records(data["calibration_records"])
    save_backtest_results(data, cv_result)
    if cv_result.get("trained"):
        save_stacking_model(cv_result)

    # ── Report ──
    print_summary(data, cv_result)

    print("Done.")


if __name__ == "__main__":
    main()

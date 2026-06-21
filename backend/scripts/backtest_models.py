#!/usr/bin/env python3
"""Walk-forward time series backtest for all WC26 Predict model components.

Evaluates each individual model (DC, Enhancer, Elo, Pi) and the fused
ensemble using an expanding-window walk-forward methodology on historical
match data.

Algorithm:
  1. Load finished matches from SQLite (JOIN matches+teams+match_results),
     sort by date.
  2. Use expanding window: train on first N matches, predict match N+1.
  3. For each prediction window:
     a. Train DC + Enhancer + Elo + Pi on window data.
     b. Predict next match with each component.
     c. Record: actual result, each model's probabilities, fused probabilities.
  4. Compute metrics: Brier Score, Log Loss, RPS, Calibration ECE.
  5. Output per-model and fused metrics.

Usage:
    python scripts/backtest_models.py --quick          # last 200 matches, fast
    python scripts/backtest_models.py --window 500      # walk-forward with 500 train window
    python scripts/backtest_models.py --full             # full backtest
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
import sqlite3

from app.services.dixon_coles import DixonColesModel
from app.services.tabular_match_model import TabularMatchEnhancer
from app.services.elo_ratings import EloRatingSystem
from app.services.pi_ratings import PiRatingWrapper

# ── Default backtest fusion weights (matching WeightConfig LEAGUE default) ──
DEFAULT_DC_WEIGHT = 0.50
DEFAULT_ELO_WEIGHT = 0.05
DEFAULT_PI_WEIGHT = 0.05

# ── DB path ──
DB_PATH = BACKEND_DIR / "data" / "local_stage2.db"

# ── Outcome mapping ──
ACTUAL_MAP = {"H": 0, "D": 1, "A": 2}
OUTCOME_KEYS = ["home_win_prob", "draw_prob", "away_win_prob"]


# ═══════════════════════════════════════════════════════════════════════════
#  Metric helpers
# ═══════════════════════════════════════════════════════════════════════════

def ranked_probability_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Ranked Probability Score for 3-class ordinal outcomes (H > D > A).

    RPS respects the ordinal nature of football outcomes better than Brier.
    Only first (r-1)=2 cumulative terms carry information; the 3rd always
    sums to 1.0.

    Parameters
    ----------
    y_true : np.ndarray, shape (3,)
        One-hot: [1,0,0] home, [0,1,0] draw, [0,0,1] away.
    y_pred : np.ndarray, shape (3,)
        Predicted probabilities [p_home, p_draw, p_away].

    Returns
    -------
    float
        RPS in [0, 1] where 0 = perfect.
    """
    cum_true = np.cumsum(y_true)
    cum_pred = np.cumsum(y_pred)
    # Only first r-1 terms carry information (3rd cum diff is always 0)
    return float(np.mean((cum_true[:2] - cum_pred[:2]) ** 2))


def brier_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Multi-class Brier score (mean squared error)."""
    return float(np.mean((y_pred - y_true) ** 2))


def log_loss_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Multi-class logarithmic loss (cross-entropy)."""
    eps = 1e-15
    y_pred = np.clip(y_pred, eps, 1 - eps)
    return float(-np.sum(y_true * np.log(y_pred)))


def calibration_ece(
    predictions: list[np.ndarray],
    actuals: list[np.ndarray],
    n_bins: int = 10,
) -> float:
    """Expected Calibration Error (ECE) for multi-class probabilities.

    Computed per-class then averaged. Each prediction's confidence is the
    maximum predicted probability. Bins are based on confidence level.

    Parameters
    ----------
    predictions : list of np.ndarray (shape (3,))
    actuals : list of np.ndarray (shape (3,))
    n_bins : int, default 10

    Returns
    -------
    float
        ECE in [0, 1]; lower is better calibrated.
    """
    if not predictions:
        return 0.0

    all_preds = np.array(predictions)  # (N, 3)
    all_actuals = np.array(actuals)    # (N, 3)
    ece_per_class: list[float] = []

    for c in range(3):
        conf = all_preds[:, c]  # predicted probability for class c
        correct = all_actuals[:, c]  # 1 if actual == c, else 0

        bin_boundaries = np.linspace(0.0, 1.0, n_bins + 1)
        ece = 0.0
        for i in range(n_bins):
            lo, hi = bin_boundaries[i], bin_boundaries[i + 1]
            in_bin = (conf > lo) & (conf <= hi)
            if in_bin.sum() == 0:
                continue
            bin_acc = float(correct[in_bin].mean())
            bin_conf = float(conf[in_bin].mean())
            ece += (in_bin.sum() / len(conf)) * abs(bin_acc - bin_conf)
        ece_per_class.append(ece)

    return float(np.mean(ece_per_class))


# ═══════════════════════════════════════════════════════════════════════════
#  Fusion simulation (mirrors the predict_match pipeline)
# ═══════════════════════════════════════════════════════════════════════════

def normalize_triplet(h: float, d: float, a: float) -> tuple[float, float, float]:
    """Normalise a probability triplet to sum to 1.0."""
    total = h + d + a
    if total <= 0:
        return (1.0 / 3, 1.0 / 3, 1.0 / 3)
    return (h / total, d / total, a / total)


def fuse_ensemble(
    dc_probs: tuple[float, float, float],
    enh_probs: tuple[float, float, float] | None,
    elo_probs: tuple[float, float, float] | None,
    pi_probs: tuple[float, float, float] | None,
    *,
    dc_weight: float = DEFAULT_DC_WEIGHT,
    elo_weight: float = DEFAULT_ELO_WEIGHT,
    pi_weight: float = DEFAULT_PI_WEIGHT,
) -> dict[str, float]:
    """Sequential fusion matching the predict_match pipeline.

    Step order matches predict_match_full.py pipeline:
      1. DC (base)
      2. DC + Enhancer  → fuse_outcome_probabilities(base_weight=dc_weight)
      3. + Elo           → fuse_elo_probabilities(elo_weight=elo_weight)
      4. + Pi            → fuse_pi_probabilities(pi_weight=pi_weight)

    Returns dict with keys home_win_prob / draw_prob / away_win_prob.
    """
    dc_h, dc_d, dc_a = dc_probs

    # Step 1: DC base
    fused_h, fused_d, fused_a = dc_h, dc_d, dc_a

    # Step 2: DC + Enhancer (if available)
    if enh_probs is not None:
        enh_h, enh_d, enh_a = enh_probs
        enh_w = 1.0 - dc_weight
        fused_h = dc_h * dc_weight + enh_h * enh_w
        fused_d = dc_d * dc_weight + enh_d * enh_w
        fused_a = dc_a * dc_weight + enh_a * enh_w
        fused_h, fused_d, fused_a = normalize_triplet(fused_h, fused_d, fused_a)

    # Step 3: + Elo (if available)
    if elo_probs is not None:
        elo_h, elo_d, elo_a = elo_probs
        fused_h = fused_h * (1.0 - elo_weight) + elo_h * elo_weight
        fused_d = fused_d * (1.0 - elo_weight) + elo_d * elo_weight
        fused_a = fused_a * (1.0 - elo_weight) + elo_a * elo_weight
        fused_h, fused_d, fused_a = normalize_triplet(fused_h, fused_d, fused_a)

    # Step 4: + Pi (if available)
    if pi_probs is not None:
        pi_h, pi_d, pi_a = pi_probs
        fused_h = fused_h * (1.0 - pi_weight) + pi_h * pi_weight
        fused_d = fused_d * (1.0 - pi_weight) + pi_d * pi_weight
        fused_a = fused_a * (1.0 - pi_weight) + pi_a * pi_weight
        fused_h, fused_d, fused_a = normalize_triplet(fused_h, fused_d, fused_a)

    return {
        "home_win_prob": fused_h,
        "draw_prob": fused_d,
        "away_win_prob": fused_a,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  Data loading
# ═══════════════════════════════════════════════════════════════════════════

def load_data(team_type: str = "national", max_rows: int | None = None) -> pd.DataFrame:
    """Load finished match data from SQLite, sorted by date ascending.

    Parameters
    ----------
    team_type : str
        Filter by team type (e.g. 'national', 'club').  Empty string = all.
    max_rows : int or None
        If set, keep only the most recent N rows (for quick mode).

    Returns
    -------
    pd.DataFrame with columns:
        home_team, away_team, home_goals, away_goals, match_date,
        competition_weight, is_neutral_venue, competition, stage
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DB_PATH}. "
            "Run train_models.py or ensure local_stage2.db exists."
        )

    team_filter = ""
    if team_type:
        team_filter = (
            f"AND ht.team_type = '{team_type}' "
            f"AND at.team_type = '{team_type}'"
        )

    conn = sqlite3.connect(str(DB_PATH))
    df = pd.read_sql_query(
        f"""
        SELECT ht.name AS home_team,
               at.name AS away_team,
               mr.home_goals,
               mr.away_goals,
               m.match_date,
               COALESCE(m.competition_weight, 1.0) AS competition_weight,
               COALESCE(m.is_neutral_venue, 0)     AS is_neutral_venue,
               m.competition,
               COALESCE(m.stage, '')               AS stage
        FROM matches m
        JOIN teams ht ON m.home_team_id = ht.id
        JOIN teams at ON m.away_team_id = at.id
        JOIN match_results mr ON m.id = mr.match_id
        WHERE m.status = 'finished'
        {team_filter}
        ORDER BY m.match_date ASC
        """,
        conn,
    )
    conn.close()

    if df.empty:
        raise ValueError("No finished matches found in the database.")

    df["match_date"] = pd.to_datetime(df["match_date"], utc=True, format="ISO8601")
    df["_actual_label"] = df.apply(
        lambda r: 0 if r.home_goals > r.away_goals
                  else 1 if r.home_goals == r.away_goals
                  else 2,
        axis=1,
    )

    if max_rows is not None and max_rows < len(df):
        df = df.tail(max_rows).reset_index(drop=True)

    print(f"  [data] Loaded {len(df)} matches, "
          f"{df.home_team.nunique()} teams, "
          f"date range: {df['match_date'].min().date()} → {df['match_date'].max().date()}",
          flush=True)
    return df


# ═══════════════════════════════════════════════════════════════════════════
#  Walk-forward backtest core
# ═══════════════════════════════════════════════════════════════════════════

def _to_onehot(label: int) -> np.ndarray:
    arr = np.zeros(3, dtype=float)
    arr[label] = 1.0
    return arr


def run_walk_forward_backtest(
    df: pd.DataFrame,
    initial_window: int,
    step: int = 1,
    *,
    dc_weight: float = DEFAULT_DC_WEIGHT,
    elo_weight: float = DEFAULT_ELO_WEIGHT,
    pi_weight: float = DEFAULT_PI_WEIGHT,
    verbose: bool = True,
) -> list[dict]:
    """Execute walk-forward backtest.

    For each test index i from initial_window to len(df)-1:
      1. Train DC + Enhancer + Elo + Pi on df[:i]
      2. Predict match at df.iloc[i] with each component
      3. Compute fused probabilities
      4. Record all results

    Parameters
    ----------
    df : pd.DataFrame
        Chronologically sorted match data.
    initial_window : int
        Number of initial matches used for the first training window.
    step : int
        Predict every `step`-th match (skip intermediate for speed).
    dc_weight, elo_weight, pi_weight : float
        Fusion blend parameters.
    verbose : bool
        Print progress every 50 iterations.

    Returns
    -------
    list[dict]
        Each entry: {
            "match_idx", "home_team", "away_team", "match_date",
            "actual_label", "actual_onehot",
            "dc_probs": [h, d, a], "enh_probs": [h, d, a],
            "elo_probs": [h, d, a], "pi_probs": [h, d, a],
            "fused_probs": [h, d, a],
        }
    """
    if len(df) < initial_window + 1:
        raise ValueError(
            f"Data has {len(df)} rows, need at least {initial_window + 1} "
            f"for initial_window={initial_window}"
        )

    n_test = len(df) - initial_window
    results: list[dict] = []
    t_start = time.perf_counter()

    test_indices = list(range(initial_window, len(df), step))

    for iteration, idx in enumerate(test_indices):
        train_df = df.iloc[:idx].reset_index(drop=True)
        test_row = df.iloc[idx]

        # ── Train models on window ──
        # Dixon-Coles
        dc = DixonColesModel()
        dc.fit(train_df)

        # TabularMatchEnhancer
        enh = TabularMatchEnhancer()
        enh.fit(train_df)

        # Elo
        elo = EloRatingSystem()
        elo.fit(train_df)

        # Pi-Rating
        pi = PiRatingWrapper()
        pi.fit(train_df)

        # ── Predict ──
        match_date = test_row["match_date"].to_pydatetime()
        is_neutral = bool(test_row["is_neutral_venue"])
        competition = str(test_row["competition"])

        # DC
        dc_pred = dc.predict_match(
            test_row["home_team"],
            test_row["away_team"],
            is_neutral_venue=is_neutral,
        )
        dc_probs = (
            float(dc_pred["home_win_prob"]),
            float(dc_pred["draw_prob"]),
            float(dc_pred["away_win_prob"]),
        )

        # Enhancer
        enh_pred = enh.predict_match(
            home_team=test_row["home_team"],
            away_team=test_row["away_team"],
            match_date=match_date,
            competition_weight=float(test_row["competition_weight"]),
            is_neutral_venue=is_neutral,
            training_df=train_df,
        )
        enh_probs = (
            float(enh_pred["home_win_prob"]),
            float(enh_pred["draw_prob"]),
            float(enh_pred["away_win_prob"]),
        )

        # Elo
        elo_pred_obj = elo.predict(
            test_row["home_team"],
            test_row["away_team"],
            is_neutral=is_neutral,
            competition_weight=float(test_row["competition_weight"]),
            competition=competition,
        )
        elo_probs = (
            float(elo_pred_obj.home_win_prob),
            float(elo_pred_obj.draw_prob),
            float(elo_pred_obj.away_win_prob),
        )

        # Pi
        pi_pred = pi.predict(
            test_row["home_team"],
            test_row["away_team"],
            is_neutral=is_neutral,
        )
        pi_probs = (
            float(pi_pred["home_win_prob"]),
            float(pi_pred["draw_prob"]),
            float(pi_pred["away_win_prob"]),
        )

        # ── Fuse ──
        fused = fuse_ensemble(
            dc_probs, enh_probs, elo_probs, pi_probs,
            dc_weight=dc_weight,
            elo_weight=elo_weight,
            pi_weight=pi_weight,
        )

        # ── Record ──
        actual_label = int(test_row["_actual_label"])
        results.append({
            "match_idx": int(idx),
            "home_team": str(test_row["home_team"]),
            "away_team": str(test_row["away_team"]),
            "match_date": str(test_row["match_date"]),
            "actual_label": actual_label,
            "actual_onehot": _to_onehot(actual_label).tolist(),
            "dc_probs": list(dc_probs),
            "enh_probs": list(enh_probs),
            "elo_probs": list(elo_probs),
            "pi_probs": list(pi_probs),
            "fused_probs": [fused["home_win_prob"], fused["draw_prob"], fused["away_win_prob"]],
        })

        if verbose and (iteration + 1) % 50 == 0:
            elapsed = time.perf_counter() - t_start
            pct = (iteration + 1) / len(test_indices) * 100
            print(
                f"  [{iteration + 1}/{len(test_indices)}] "
                f"{pct:.0f}%  elapsed={elapsed:.0f}s",
                flush=True,
            )

    total_elapsed = time.perf_counter() - t_start
    print(
        f"  Backtest complete: {len(results)} predictions "
        f"in {total_elapsed:.1f}s",
        flush=True,
    )
    return results


# ═══════════════════════════════════════════════════════════════════════════
#  Metric computation
# ═══════════════════════════════════════════════════════════════════════════

def compute_component_metrics(
    results: list[dict],
) -> dict[str, dict[str, float]]:
    """Compute Brier, LogLoss, RPS, and Calibration ECE per component.

    Returns nested dict:
        {component_name: {brier: ..., log_loss: ..., rps: ..., calibration_ece: ...}}
    """
    components = ["dc", "enh", "elo", "pi", "fused"]
    labels = {
        "dc": "dc",
        "enh": "enhancer",
        "elo": "elo",
        "pi": "pi_rating",
        "fused": "fused",
    }
    metrics: dict[str, dict[str, float]] = {}

    for comp_key in components:
        label = labels[comp_key]
        all_preds: list[np.ndarray] = []
        all_actuals: list[np.ndarray] = []

        for r in results:
            actual = np.array(r["actual_onehot"], dtype=float)
            pred = np.array(r[f"{comp_key}_probs"], dtype=float)
            all_actuals.append(actual)
            all_preds.append(pred)

        preds_arr = np.array(all_preds)
        actuals_arr = np.array(all_actuals)

        # Brier (multi-class): average squared error per class
        brier_val = float(np.mean((preds_arr - actuals_arr) ** 2))

        # Log loss
        eps = 1e-15
        clipped = np.clip(preds_arr, eps, 1 - eps)
        ll_val = float(-np.mean(np.sum(actuals_arr * np.log(clipped), axis=1)))

        # RPS
        rps_vals = [
            ranked_probability_score(actuals_arr[i], preds_arr[i])
            for i in range(len(preds_arr))
        ]
        rps_val = float(np.mean(rps_vals))

        # Calibration ECE
        ece_val = calibration_ece(all_preds, all_actuals)

        metrics[label] = {
            "brier": round(brier_val, 4),
            "log_loss": round(ll_val, 4),
            "rps": round(rps_val, 4),
            "calibration_ece": round(ece_val, 4),
        }

    return metrics


def print_metrics(metrics: dict[str, dict[str, float]]) -> None:
    """Pretty-print the metrics table."""
    comp_names = list(metrics.keys())
    metric_names = list(metrics[comp_names[0]].keys())

    # Header
    header = f"{'Component':<14}" + "".join(f"{m:>16}" for m in metric_names)
    sep_line = "-" * len(header)

    print()
    print(sep_line)
    print("BACKTEST METRICS")
    print(sep_line)
    print(header)
    print(sep_line)
    for comp in comp_names:
        vals = "".join(f"{metrics[comp][m]:>16.4f}" for m in metric_names)
        print(f"{comp:<14}{vals}")
    print(sep_line)
    print()
    print("  Lower is better for all metrics (Brier, LogLoss, RPS, ECE).")
    print()


def print_yaml_summary(
    results_count: int,
    initial_window: int,
    metrics: dict[str, dict[str, float]],
) -> None:
    """Print a YAML-formatted summary block."""
    fused = metrics.get("fused", {})
    dc_m = metrics.get("dc", {})
    enh_m = metrics.get("enhancer", {})
    elo_m = metrics.get("elo", {})
    pi_m = metrics.get("pi_rating", {})

    print("---")
    print("backtest:")
    print(f"  sample_size: {results_count}")
    print(f"  window_type: expanding")
    print(f"  initial_window: {initial_window}")
    print("  metrics:")
    print("    brier:")
    print(f"      dc: {dc_m.get('brier', 0):.4f}")
    print(f"      enhancer: {enh_m.get('brier', 0):.4f}")
    print(f"      elo: {elo_m.get('brier', 0):.4f}")
    print(f"      pi: {pi_m.get('brier', 0):.4f}")
    print(f"      fused: {fused.get('brier', 0):.4f}")
    print("    log_loss:")
    print(f"      dc: {dc_m.get('log_loss', 0):.4f}")
    print(f"      enhancer: {enh_m.get('log_loss', 0):.4f}")
    print(f"      elo: {elo_m.get('log_loss', 0):.4f}")
    print(f"      pi: {pi_m.get('log_loss', 0):.4f}")
    print(f"      fused: {fused.get('log_loss', 0):.4f}")
    print("    rps:")
    print(f"      dc: {dc_m.get('rps', 0):.4f}")
    print(f"      enhancer: {enh_m.get('rps', 0):.4f}")
    print(f"      elo: {elo_m.get('rps', 0):.4f}")
    print(f"      pi: {pi_m.get('rps', 0):.4f}")
    print(f"      fused: {fused.get('rps', 0):.4f}")
    print(f"    calibration_ece: {fused.get('calibration_ece', 0):.4f}")


# ═══════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="WC26 Predict — walk-forward time series backtest",
    )
    p.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: use last 200 matches, smaller initial window (100)",
    )
    p.add_argument(
        "--window",
        type=int,
        default=None,
        help="Initial training window size (default: auto based on mode)",
    )
    p.add_argument(
        "--full",
        action="store_true",
        help="Full backtest: use all available data with window=500, step=3",
    )
    p.add_argument(
        "--step",
        type=int,
        default=1,
        help="Predict every N-th match (default: 1 = all matches)",
    )
    p.add_argument(
        "--team-type",
        default="national",
        help="Team type filter (default: national)",
    )
    p.add_argument(
        "--dc-weight",
        type=float,
        default=DEFAULT_DC_WEIGHT,
        help=f"DC weight in DC+Enhancer fusion (default: {DEFAULT_DC_WEIGHT})",
    )
    p.add_argument(
        "--elo-weight",
        type=float,
        default=DEFAULT_ELO_WEIGHT,
        help=f"Elo blend weight (default: {DEFAULT_ELO_WEIGHT})",
    )
    p.add_argument(
        "--pi-weight",
        type=float,
        default=DEFAULT_PI_WEIGHT,
        help=f"Pi-Rating blend weight (default: {DEFAULT_PI_WEIGHT})",
    )
    p.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    p.add_argument(
        "--save-results",
        type=str,
        default=None,
        help="Path to save detailed per-match results as JSON",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # ── Determine mode ──
    if args.full:
        initial_window = 500
        step = max(1, args.step or 3)
        max_rows = None
        label = "full"
    elif args.quick:
        initial_window = 100
        step = max(1, args.step or 1)
        max_rows = 200
        label = "quick"
    elif args.window is not None:
        initial_window = args.window
        step = max(1, args.step)
        max_rows = None
        label = f"window-{initial_window}"
    else:
        # Sensible default
        initial_window = 300
        step = max(1, args.step)
        max_rows = 500
        label = "default"

    print("=" * 60)
    print(f"  WC26 Predict — Walk-Forward Backtest  [{label}]")
    print(f"    initial_window: {initial_window}")
    print(f"    step:           {step}")
    print(f"    max_rows:       {max_rows or 'all'}")
    print(f"    team_type:      {args.team_type}")
    print(f"    fusion weights: DC={args.dc_weight}, Elo={args.elo_weight}, Pi={args.pi_weight}")
    print("=" * 60)
    print()

    # ── Load data ──
    print("[1] Loading data")
    df = load_data(team_type=args.team_type, max_rows=max_rows)

    # Validate we have enough data
    min_required = initial_window + 1
    if len(df) < min_required:
        print(
            f"  ERROR: Only {len(df)} matches available, need at least "
            f"{min_required} for initial_window={initial_window}.",
            flush=True,
        )
        sys.exit(1)

    # ── Run backtest ──
    print(f"\n[2] Running walk-forward backtest ({len(df) - initial_window} predictions)")
    results = run_walk_forward_backtest(
        df,
        initial_window=initial_window,
        step=step,
        dc_weight=args.dc_weight,
        elo_weight=args.elo_weight,
        pi_weight=args.pi_weight,
    )

    # ── Compute metrics ──
    print("\n[3] Computing metrics")
    metrics = compute_component_metrics(results)

    # ── Output ──
    if args.output == "json":
        output = {
            "backtest_config": {
                "label": label,
                "initial_window": initial_window,
                "step": step,
                "team_type": args.team_type,
                "fusion_weights": {
                    "dc": args.dc_weight,
                    "elo": args.elo_weight,
                    "pi": args.pi_weight,
                },
            },
            "results_count": len(results),
            "metrics": metrics,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print_metrics(metrics)
        print_yaml_summary(len(results), initial_window, metrics)

    # ── Save detailed results (optional) ──
    if args.save_results:
        path = Path(args.save_results)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Convert numpy arrays to lists for JSON serialization
        serializable = []
        for r in results:
            entry = dict(r)
            entry["actual_onehot"] = list(entry["actual_onehot"])
            serializable.append(entry)
        path.write_text(
            json.dumps(serializable, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\n  Detailed results saved to: {path}", flush=True)


if __name__ == "__main__":
    main()

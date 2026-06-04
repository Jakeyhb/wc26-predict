#!/usr/bin/env python3
"""Grid search over fusion weights to find optimal ensemble blend parameters.

Conducts a walk-forward backtest for each weight combination, selecting the
set that minimises the multi-class Brier score.

Strategy:
  1. ONE walk-forward pass stores per-match component probabilities.
  2. Grid search evaluates every (dc_weight, elo_weight, pi_weight) combo
     by re-blending stored probabilities — no re-training needed.
  3. Selects the combination with the lowest average Brier score.

Usage:
    python scripts/optimize_fusion_weights.py --quick      # last 300 matches, reduced grid
    python scripts/optimize_fusion_weights.py --window 500  # walk-forward with 500 train window
    python scripts/optimize_fusion_weights.py --full         # all data, full grid
"""
from __future__ import annotations

import argparse
import itertools
import json
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

# ── DB path ──
DB_PATH = BACKEND_DIR / "data" / "local_stage2.db"
ARTIFACTS_DIR = BACKEND_DIR / "artifacts"

# ── Search grid (full) ──
FULL_DC_GRID = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]
FULL_ELO_GRID = [0.02, 0.05, 0.08, 0.10, 0.15]
FULL_PI_GRID = [0.02, 0.05, 0.08, 0.10, 0.15]

# ── Search grid (quick) ──
QUICK_DC_GRID = [0.45, 0.50, 0.55, 0.60, 0.65]
QUICK_ELO_GRID = [0.02, 0.05, 0.10]
QUICK_PI_GRID = [0.02, 0.05, 0.10]


# ═══════════════════════════════════════════════════════════════════════════
#  Normalisation / fusion helpers
# ═══════════════════════════════════════════════════════════════════════════

def normalize_triplet(h: float, d: float, a: float) -> tuple[float, float, float]:
    """Normalise a probability triplet to sum to 1.0."""
    total = h + d + a
    if total <= 0:
        return (1.0 / 3, 1.0 / 3, 1.0 / 3)
    return (h / total, d / total, a / total)


def simulate_fused_probs(
    dc_probs: tuple[float, float, float],
    enh_probs: tuple[float, float, float],
    elo_probs: tuple[float, float, float] | None,
    pi_probs: tuple[float, float, float] | None,
    *,
    dc_weight: float,
    elo_weight: float,
    pi_weight: float,
) -> np.ndarray:
    """Simulate the sequential fusion pipeline with given weights.

    Mirrors ``fuse_outcome_probabilities`` → ``fuse_elo_probabilities`` →
    ``fuse_pi_probabilities`` from the main prediction pipeline.

    Returns np.ndarray shape (3,) = [p_home, p_draw, p_away].
    """
    dc_h, dc_d, dc_a = dc_probs
    enh_h, enh_d, enh_a = enh_probs

    # Step 1: DC + Enhancer
    enh_w = 1.0 - dc_weight
    f_h = dc_h * dc_weight + enh_h * enh_w
    f_d = dc_d * dc_weight + enh_d * enh_w
    f_a = dc_a * dc_weight + enh_a * enh_w
    f_h, f_d, f_a = normalize_triplet(f_h, f_d, f_a)

    # Step 2: + Elo (if available)
    if elo_probs is not None:
        elo_h, elo_d, elo_a = elo_probs
        f_h = f_h * (1.0 - elo_weight) + elo_h * elo_weight
        f_d = f_d * (1.0 - elo_weight) + elo_d * elo_weight
        f_a = f_a * (1.0 - elo_weight) + elo_a * elo_weight
        f_h, f_d, f_a = normalize_triplet(f_h, f_d, f_a)

    # Step 3: + Pi (if available)
    if pi_probs is not None:
        pi_h, pi_d, pi_a = pi_probs
        f_h = f_h * (1.0 - pi_weight) + pi_h * pi_weight
        f_d = f_d * (1.0 - pi_weight) + pi_d * pi_weight
        f_a = f_a * (1.0 - pi_weight) + pi_a * pi_weight
        f_h, f_d, f_a = normalize_triplet(f_h, f_d, f_a)

    return np.array([f_h, f_d, f_a], dtype=float)


# ═══════════════════════════════════════════════════════════════════════════
#  Data loading
# ═══════════════════════════════════════════════════════════════════════════

def load_data(team_type: str = "national", max_rows: int | None = None) -> pd.DataFrame:
    """Load finished match data from SQLite, sorted by date ascending.

    Same query as backtest_models.py / train_models.py.
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
          f"{df.home_team.nunique()} teams",
          flush=True)
    return df


# ═══════════════════════════════════════════════════════════════════════════
#  Walk-forward: collect component probabilities
# ═══════════════════════════════════════════════════════════════════════════

def collect_component_probs(
    df: pd.DataFrame,
    initial_window: int,
    step: int = 1,
    verbose: bool = True,
) -> list[dict]:
    """Perform one walk-forward pass, recording component-level probabilities.

    Returns a list of dicts, each with keys:
      actual_onehot : np.ndarray (3,)
      dc / enh / elo / pi : np.ndarray (3,)  probabilities per component

    These can later be re-blended with arbitrary fusion weights without
    re-running the expensive model training.
    """
    n_total = len(df)
    if n_total < initial_window + 1:
        raise ValueError(
            f"Data has {n_total} rows, need at least {initial_window + 1}"
        )

    records: list[dict] = []
    test_indices = list(range(initial_window, n_total, step))
    t_start = time.perf_counter()

    for iteration, idx in enumerate(test_indices):
        train_df = df.iloc[:idx].reset_index(drop=True)
        test_row = df.iloc[idx]

        # ── Train models on window ──
        dc = DixonColesModel()
        dc.fit(train_df)

        enh = TabularMatchEnhancer()
        enh.fit(train_df)

        elo = EloRatingSystem()
        elo.fit(train_df)

        pi = PiRatingWrapper()
        pi.fit(train_df)

        # ── Predict each component ──
        match_date = test_row["match_date"].to_pydatetime()
        is_neutral = bool(test_row["is_neutral_venue"])
        competition = str(test_row["competition"])

        # DC
        dc_pred = dc.predict_match(
            test_row["home_team"], test_row["away_team"],
            is_neutral_venue=is_neutral,
        )
        dc_arr = np.array([
            dc_pred["home_win_prob"], dc_pred["draw_prob"], dc_pred["away_win_prob"],
        ], dtype=float)

        # Enhancer
        enh_pred = enh.predict_match(
            home_team=test_row["home_team"],
            away_team=test_row["away_team"],
            match_date=match_date,
            competition_weight=float(test_row["competition_weight"]),
            is_neutral_venue=is_neutral,
            training_df=train_df,
        )
        enh_arr = np.array([
            enh_pred["home_win_prob"], enh_pred["draw_prob"], enh_pred["away_win_prob"],
        ], dtype=float)

        # Elo
        elo_pred_obj = elo.predict(
            test_row["home_team"], test_row["away_team"],
            is_neutral=is_neutral,
            competition_weight=float(test_row["competition_weight"]),
            competition=competition,
        )
        elo_arr = np.array([
            elo_pred_obj.home_win_prob, elo_pred_obj.draw_prob, elo_pred_obj.away_win_prob,
        ], dtype=float)

        # Pi
        pi_pred = pi.predict(
            test_row["home_team"], test_row["away_team"],
            is_neutral=is_neutral,
        )
        pi_arr = np.array([
            pi_pred["home_win_prob"], pi_pred["draw_prob"], pi_pred["away_win_prob"],
        ], dtype=float)

        # Actual one-hot
        actual_label = int(test_row["_actual_label"])
        actual_onehot = np.zeros(3, dtype=float)
        actual_onehot[actual_label] = 1.0

        records.append({
            "actual_onehot": actual_onehot,
            "dc": dc_arr,
            "enh": enh_arr,
            "elo": elo_arr,
            "pi": pi_arr,
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
        f"  Component collection complete: {len(records)} predictions "
        f"in {total_elapsed:.1f}s",
        flush=True,
    )
    return records


# ═══════════════════════════════════════════════════════════════════════════
#  Grid search
# ═══════════════════════════════════════════════════════════════════════════

def evaluate_weight_combo(
    records: list[dict],
    dc_weight: float,
    elo_weight: float,
    pi_weight: float,
) -> float:
    """Compute average Brier score for a single weight combination.

    Uses pre-computed component probabilities from ``records`` — no
    model training needed.
    """
    n = len(records)
    total_brier = 0.0

    for rec in records:
        fused = simulate_fused_probs(
            tuple(rec["dc"].tolist()),
            tuple(rec["enh"].tolist()),
            tuple(rec["elo"].tolist()),
            tuple(rec["pi"].tolist()),
            dc_weight=dc_weight,
            elo_weight=elo_weight,
            pi_weight=pi_weight,
        )
        brier = float(np.mean((fused - rec["actual_onehot"]) ** 2))
        total_brier += brier

    return total_brier / n


def grid_search(
    records: list[dict],
    dc_grid: list[float],
    elo_grid: list[float],
    pi_grid: list[float],
) -> tuple[dict[str, float], float, list[dict]]:
    """Exhaustive grid search over fusion weight combinations.

    Returns
    -------
    best_weights : dict  {dc, elo, pi}
    best_brier : float
    all_results : list of dict  {dc, elo, pi, brier}
    """
    total_combos = len(dc_grid) * len(elo_grid) * len(pi_grid)
    print(f"  Grid search: {total_combos} combinations "
          f"(dc={len(dc_grid)}, elo={len(elo_grid)}, pi={len(pi_grid)})",
          flush=True)

    best_brier = float("inf")
    best_weights: dict[str, float] = {}
    all_results: list[dict] = []
    t_start = time.perf_counter()

    for combo_idx, (dc_w, elo_w, pi_w) in enumerate(
        itertools.product(dc_grid, elo_grid, pi_grid)
    ):
        brier = evaluate_weight_combo(records, dc_w, elo_w, pi_w)
        all_results.append({
            "dc": dc_w,
            "elo": elo_w,
            "pi": pi_w,
            "brier": round(brier, 5),
        })

        if brier < best_brier:
            best_brier = brier
            best_weights = {"dc": dc_w, "elo": elo_w, "pi": pi_w}

        # Progress every 25 combos
        if (combo_idx + 1) % 25 == 0:
            elapsed = time.perf_counter() - t_start
            pct = (combo_idx + 1) / total_combos * 100
            print(
                f"    [{combo_idx + 1}/{total_combos}] "
                f"{pct:.0f}%  best_brier={best_brier:.5f}  "
                f"elapsed={elapsed:.0f}s",
                flush=True,
            )

    total_elapsed = time.perf_counter() - t_start
    print(
        f"  Grid search complete: {total_combos} combos in {total_elapsed:.1f}s",
        flush=True,
    )

    # Sort by Brier ascending and keep top results for reporting
    all_results.sort(key=lambda x: x["brier"])

    return best_weights, best_brier, all_results


# ═══════════════════════════════════════════════════════════════════════════
#  Reporting
# ═══════════════════════════════════════════════════════════════════════════

def compute_effective_weights(
    dc_weight: float,
    elo_weight: float,
    pi_weight: float,
) -> dict[str, float]:
    """Compute effective percentage contribution of each component.

    After sequential fusion the effective weights are:
      DC:        dc_weight * (1-elo) * (1-pi)
      Enhancer:  (1-dc)     * (1-elo) * (1-pi)
      Elo:       elo_weight * (1-pi)
      Pi:        pi_weight

    These sum to 1.0 (ignoring normalisation adjustments).
    """
    dc_eff = dc_weight * (1.0 - elo_weight) * (1.0 - pi_weight)
    enh_eff = (1.0 - dc_weight) * (1.0 - elo_weight) * (1.0 - pi_weight)
    elo_eff = elo_weight * (1.0 - pi_weight)
    pi_eff = pi_weight
    total = dc_eff + enh_eff + elo_eff + pi_eff
    return {
        "dc": dc_eff / total * 100,
        "enhancer": enh_eff / total * 100,
        "elo": elo_eff / total * 100,
        "pi": pi_eff / total * 100,
    }


def print_results(
    best_weights: dict[str, float],
    best_brier: float,
    all_results: list[dict],
    n_records: int,
) -> None:
    """Print the optimisation results table."""
    eff = compute_effective_weights(
        best_weights["dc"],
        best_weights["elo"],
        best_weights["pi"],
    )

    print()
    print("=" * 60)
    print("  OPTIMAL FUSION WEIGHTS")
    print("=" * 60)
    print(f"  dc_vs_enhancer: {best_weights['dc']:.2f} "
          f"(DC {best_weights['dc']:.0%} / Enhancer {1 - best_weights['dc']:.0%})")
    print(f"  elo_blend:      {best_weights['elo']:.2f}")
    print(f"  pi_blend:       {best_weights['pi']:.2f}")
    print()
    print("  Effective weights:")
    print(f"    DC:       {eff['dc']:.2f}%")
    print(f"    Enhancer: {eff['enhancer']:.2f}%")
    print(f"    Elo:      {eff['elo']:.2f}%")
    print(f"    Pi:       {eff['pi']:.2f}%")
    print()
    print(f"  Best (average) Brier: {best_brier:.5f}")
    print(f"  Tested on: {n_records} walk-forward predictions")
    print()

    # Top-10 table
    print("  Top 10 weight combinations:")
    print(f"  {'Rank':<6} {'DC':<8} {'Elo':<8} {'Pi':<8} {'Brier':<10}")
    print(f"  {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*10}")
    for rank, entry in enumerate(all_results[:10], 1):
        print(f"  {rank:<6} {entry['dc']:<8.2f} {entry['elo']:<8.2f} "
              f"{entry['pi']:<8.2f} {entry['brier']:<10.5f}")

    # Bottom-3 table
    print()
    print("  Worst 3 weight combinations:")
    print(f"  {'Rank':<6} {'DC':<8} {'Elo':<8} {'Pi':<8} {'Brier':<10}")
    print(f"  {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*10}")
    for rank, entry in enumerate(
        sorted(all_results, key=lambda x: x["brier"], reverse=True)[:3], 1
    ):
        print(f"  {rank:<6} {entry['dc']:<8.2f} {entry['elo']:<8.2f} "
              f"{entry['pi']:<8.2f} {entry['brier']:<10.5f}")
    print()


# ═══════════════════════════════════════════════════════════════════════════
#  Save results
# ═══════════════════════════════════════════════════════════════════════════

def save_fusion_weights(
    best_weights: dict[str, float],
    best_brier: float,
    effective_weights: dict[str, float],
    n_records: int,
) -> Path:
    """Save optimal weights to artifacts/fusion_weights.json.

    Returns the path to the saved file.
    """
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS_DIR / "fusion_weights.json"

    payload = {
        "version": "2.0",
        "optimized_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": "grid_search_walk_forward_brier",
        "parameters": {
            "dc_vs_enhancer": best_weights["dc"],
            "elo_blend": best_weights["elo"],
            "pi_blend": best_weights["pi"],
        },
        "effective_weights_pct": effective_weights,
        "best_brier": round(best_brier, 5),
        "tested_on_predictions": n_records,
        "notes": (
            "DC+Enhancer fusion: dc_weight applied to DC, (1-dc_weight) to Enhancer. "
            "Elo and Pi blended sequentially with their respective weights. "
            "Effective weights account for sequential dilution."
        ),
    }

    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


# ═══════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="WC26 Predict — grid search optimisation of fusion weights",
    )
    p.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: last 300 matches, reduced grid (runs fast)",
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
        help="Full optimisation: all data, full grid, step=3",
    )
    p.add_argument(
        "--step",
        type=int,
        default=1,
        help="Predict every N-th match (default: 1)",
    )
    p.add_argument(
        "--team-type",
        default="national",
        help="Team type filter (default: national)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print optimal weights without saving to file",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # ── Determine mode ──
    if args.full:
        initial_window = 500
        step = max(1, args.step or 3)
        max_rows = None
        dc_grid = FULL_DC_GRID
        elo_grid = FULL_ELO_GRID
        pi_grid = FULL_PI_GRID
        label = "full"
    elif args.quick:
        initial_window = 150
        step = max(1, args.step or 1)
        max_rows = 300
        dc_grid = QUICK_DC_GRID
        elo_grid = QUICK_ELO_GRID
        pi_grid = QUICK_PI_GRID
        label = "quick"
    elif args.window is not None:
        initial_window = args.window
        step = max(1, args.step)
        max_rows = None
        dc_grid = FULL_DC_GRID
        elo_grid = FULL_ELO_GRID
        pi_grid = FULL_PI_GRID
        label = f"window-{initial_window}"
    else:
        # Sensible default: quick but meaningful
        initial_window = 200
        step = 1
        max_rows = 400
        dc_grid = QUICK_DC_GRID
        elo_grid = QUICK_ELO_GRID
        pi_grid = QUICK_PI_GRID
        label = "default"

    total_combos = len(dc_grid) * len(elo_grid) * len(pi_grid)

    print("=" * 60)
    print(f"  WC26 Predict — Fusion Weight Optimisation  [{label}]")
    print(f"    initial_window: {initial_window}")
    print(f"    step:           {step}")
    print(f"    max_rows:       {max_rows or 'all'}")
    print(f"    team_type:      {args.team_type}")
    print(f"    grid size:      {total_combos} combinations")
    print(f"    dc_grid:        {dc_grid}")
    print(f"    elo_grid:       {elo_grid}")
    print(f"    pi_grid:        {pi_grid}")
    print("=" * 60)
    print()

    # ── 1. Load data ──
    print("[1] Loading data")
    df = load_data(team_type=args.team_type, max_rows=max_rows)

    min_required = initial_window + 1
    if len(df) < min_required:
        print(
            f"  ERROR: Only {len(df)} matches, need at least "
            f"{min_required} for initial_window={initial_window}.",
            flush=True,
        )
        sys.exit(1)

    # ── 2. Collect component probabilities (single walk-forward pass) ──
    print(f"\n[2] Collecting component probabilities "
          f"({len(df) - initial_window} predictions)")
    records = collect_component_probs(
        df,
        initial_window=initial_window,
        step=step,
    )

    # ── 3. Grid search ──
    print(f"\n[3] Grid search over {total_combos} weight combinations")
    best_weights, best_brier, all_results = grid_search(
        records,
        dc_grid=dc_grid,
        elo_grid=elo_grid,
        pi_grid=pi_grid,
    )

    # ── 4. Report ──
    print("[4] Results")
    print_results(best_weights, best_brier, all_results, len(records))

    # ── 5. Save ──
    if not args.dry_run:
        eff = compute_effective_weights(
            best_weights["dc"], best_weights["elo"], best_weights["pi"],
        )
        save_path = save_fusion_weights(
            best_weights, best_brier, eff, len(records),
        )
        print(f"  Saved to: {save_path}")
    else:
        print("  [dry-run] Not saved.")


if __name__ == "__main__":
    main()

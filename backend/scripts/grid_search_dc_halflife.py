#!/usr/bin/env python3
"""grid_search_dc_halflife.py — Walk-forward grid search for optimal DC half-life.

Finds the best half_life_days for Dixon-Coles time decay by minimising
Brier score on 58 completed WC26 matches via time-series cross-validation.

Methodology (two-phase):
  1. Coarse: single-fit evaluation — fit once per half-life on all pre-WC26
     data, evaluate all 58 WC26 matches. Quick ranking (~11 fits).
  2. Fine: walk-forward CV for top candidates — for each test match, train
     only on data before that match's date. True out-of-sample evaluation.

Metrics: Brier score (primary), LogLoss, direction accuracy.
Breakdowns: overall, group-stage only, knockout only.

Usage:
    python scripts/grid_search_dc_halflife.py
    python scripts/grid_search_dc_halflife.py --phase fine --halflife 90,120,180
    python scripts/grid_search_dc_halflife.py --phase coarse --quick  # skip fine
"""

from __future__ import annotations

import argparse
import json
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

# ── Paths ──
DB_PATH = BACKEND_DIR / "data" / "local_stage2.db"
CONFIG_DIR = BACKEND_DIR / "app" / "configs"
CONFIG_PATH = CONFIG_DIR / "dc_params.json"

# ── Grid ──
COARSE_HALF_LIVES = [30, 60, 90, 120, 180, 270, 365, 540, 730, 1095, 1460]
FINE_CANDIDATE_COUNT = 5  # number of top candidates to walk-forward

# ── Constants ──
WC26_COMPETITION = "FIFA World Cup 2026"
KO_STAGES = {"Round of 32", "Round of 16", "Quarter-finals", "Semi-finals", "Final"}


# ═══════════════════════════════════════════════════════════════════════
#  Data loading
# ═══════════════════════════════════════════════════════════════════════

def load_all_training_data(min_date: str = "2020-01-01") -> pd.DataFrame:
    """Load finished national-team matches from SQLite.

    Args:
        min_date: Minimum match date (YYYY-MM-DD). Default 2020-01-01
                  keeps the dataset manageable for grid search (>250 teams
                  still need significant optimizer iterations).
    """
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
    """Load WC26 matches that have results (our evaluation targets)."""
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
    print(f"  WC26 evaluation matches: {len(df)} ({_stage_summary(df)})")
    return df


def _stage_summary(df: pd.DataFrame) -> str:
    group_count = sum(1 for s in df["stage"] if s not in KO_STAGES)
    ko_count = sum(1 for s in df["stage"] if s in KO_STAGES)
    return f"{group_count} group + {ko_count} KO"


# ═══════════════════════════════════════════════════════════════════════
#  Evaluation helpers
# ═══════════════════════════════════════════════════════════════════════

def evaluate_model(
    model: DixonColesModel,
    eval_df: pd.DataFrame,
) -> dict[str, Any]:
    """Evaluate a fitted model on evaluation matches.

    Returns brier_score, log_loss, direction_accuracy, and per-match details.
    """
    brier_scores: list[float] = []
    log_losses: list[float] = []
    correct_directions = 0
    home_correct = draw_correct = away_correct = 0
    home_total = draw_total = away_total = 0
    details: list[dict] = []

    for row in eval_df.itertuples(index=False):
        pred = model.predict_match(
            row.home_team, row.away_team, bool(row.is_neutral_venue)
        )
        probs = np.array(
            [pred["home_win_prob"], pred["draw_prob"], pred["away_win_prob"]],
            dtype=float,
        )

        # Determine actual outcome
        if row.home_goals > row.away_goals:
            actual_idx = 0
            home_total += 1
        elif row.home_goals == row.away_goals:
            actual_idx = 1
            draw_total += 1
        else:
            actual_idx = 2
            away_total += 1

        actual = np.zeros(3)
        actual[actual_idx] = 1.0

        brier = float(((probs - actual) ** 2).sum())
        logl = float(-np.log(max(probs[actual_idx], 1e-12)))
        brier_scores.append(brier)
        log_losses.append(logl)

        predicted_idx = int(np.argmax(probs))
        if predicted_idx == actual_idx:
            correct_directions += 1
            if actual_idx == 0:
                home_correct += 1
            elif actual_idx == 1:
                draw_correct += 1
            else:
                away_correct += 1

        details.append({
            "match": f"{row.home_team} vs {row.away_team}",
            "date": str(row.match_date.date()),
            "stage": row.stage,
            "actual": f"{int(row.home_goals)}-{int(row.away_goals)}",
            "pred_home": round(float(probs[0]), 4),
            "pred_draw": round(float(probs[1]), 4),
            "pred_away": round(float(probs[2]), 4),
            "brier": round(brier, 5),
            "direction": "correct" if predicted_idx == actual_idx else "wrong",
        })

    n = len(eval_df)
    return {
        "n_matches": n,
        "brier_score": float(np.mean(brier_scores)),
        "log_loss": float(np.mean(log_losses)),
        "direction_accuracy": correct_directions / n,
        "direction_counts": {
            "correct": correct_directions,
            "wrong": n - correct_directions,
            "home": f"{home_correct}/{home_total}",
            "draw": f"{draw_correct}/{draw_total}",
            "away": f"{away_correct}/{away_total}",
        },
        "details": details,
    }


def evaluate_by_stage(
    model: DixonColesModel,
    eval_df: pd.DataFrame,
) -> dict[str, Any]:
    """Evaluate separately for group stage and knockout stage."""
    group_df = eval_df[~eval_df["stage"].isin(KO_STAGES)]
    ko_df = eval_df[eval_df["stage"].isin(KO_STAGES)]

    result = {"overall": evaluate_model(model, eval_df)}
    if not group_df.empty:
        result["group_stage"] = evaluate_model(model, group_df)
    if not ko_df.empty:
        result["knockout"] = evaluate_model(model, ko_df)
    return result


# ═══════════════════════════════════════════════════════════════════════
#  Phase 1: Coarse grid (single-fit evaluation)
# ═══════════════════════════════════════════════════════════════════════

def run_coarse_grid(
    train_df: pd.DataFrame,
    eval_df: pd.DataFrame,
    half_lives: list[int],
) -> list[dict[str, Any]]:
    """Single-fit evaluation for each half-life.

    Fits once on all training data (up to max eval date), then evaluates
    all WC26 matches. Fast ranking — used to narrow the search space.

    NOTE: The single-fit approach has data leakage (future matches in
    training data) so absolute Brier values are optimistic. But relative
    ranking across half-life values is preserved for coarse comparison.
    """
    # Truncate training data at max WC26 date to avoid future leakage
    # (even though we're fitting once, we don't use post-WC26 data)
    max_eval_date = eval_df["match_date"].max()
    train_cut = train_df[train_df["match_date"] <= max_eval_date].copy()
    print(f"  Training window: {train_cut['match_date'].min().date()} -> "
          f"{train_cut['match_date'].max().date()} ({len(train_cut):,} matches)")

    results: list[dict[str, Any]] = []
    for i, hl in enumerate(half_lives):
        t0 = time.perf_counter()
        print(f"  [{i+1}/{len(half_lives)}] half_life={hl}d ...", end=" ", flush=True)

        model = DixonColesModel(half_life_days=hl)
        fit_result = model.fit(train_cut)
        eval_result = evaluate_by_stage(model, eval_df)

        elapsed = time.perf_counter() - t0
        overall = eval_result["overall"]
        print(
            f"Brier={overall['brier_score']:.4f}  "
            f"LogLoss={overall['log_loss']:.4f}  "
            f"Dir={overall['direction_accuracy']:.1%}  "
            f"({elapsed:.1f}s)"
        )

        results.append({
            "half_life_days": hl,
            "overall": {
                "brier_score": overall["brier_score"],
                "log_loss": overall["log_loss"],
                "direction_accuracy": overall["direction_accuracy"],
                "direction_counts": overall["direction_counts"],
            },
            "group_stage": _strip_details(eval_result.get("group_stage")),
            "knockout": _strip_details(eval_result.get("knockout")),
            "fit_converged": fit_result.converged,
            "fit_time_s": round(elapsed, 1),
        })

    return results


def _strip_details(result: dict | None) -> dict | None:
    """Remove per-match details for compact storage."""
    if result is None:
        return None
    return {k: v for k, v in result.items() if k != "details"}


# ═══════════════════════════════════════════════════════════════════════
#  Phase 2: Fine walk-forward CV
# ═══════════════════════════════════════════════════════════════════════

def run_walk_forward(
    train_df: pd.DataFrame,
    eval_df: pd.DataFrame,
    half_lives: list[int],
) -> list[dict[str, Any]]:
    """True walk-forward cross-validation.

    For each test match (ordered by date), train only on data before that
    match's date. This is the gold-standard evaluation — no data leakage.
    """
    # Get unique match dates in chronological order
    unique_dates = sorted(eval_df["match_date"].dt.normalize().unique())
    print(f"  Walk-forward over {len(unique_dates)} unique dates x "
          f"{len(half_lives)} half-lives = {len(unique_dates) * len(half_lives)} fits")

    results: list[dict[str, Any]] = []
    for hl in half_lives:
        t0 = time.perf_counter()
        print(f"\n  half_life={hl}d:", flush=True)

        all_details: list[dict] = []
        total_brier = 0.0
        total_logl = 0.0
        correct = 0
        total = 0

        for date_val in unique_dates:
            # Matches on this date
            day_matches = eval_df[
                eval_df["match_date"].dt.normalize() == date_val
            ]

            # Training data: all matches before this date
            train_cut = train_df[
                train_df["match_date"].dt.normalize() < date_val
            ]
            if len(train_cut) < 100:
                print(f"    WARN {date_val.date()}: only {len(train_cut)} training rows, skipping")
                continue

            model = DixonColesModel(half_life_days=hl)
            model.fit(train_cut)

            eval_result = evaluate_model(model, day_matches)
            all_details.extend(eval_result["details"])

            n = eval_result["n_matches"]
            total_brier += eval_result["brier_score"] * n
            total_logl += eval_result["log_loss"] * n
            correct += eval_result["direction_counts"]["correct"]
            total += n

            # Progress indicator
            bar = "#" if eval_result["direction_accuracy"] >= 0.5 else "."
            print(
                f"    {date_val.date()}  {n} matches  "
                f"Brier={eval_result['brier_score']:.4f}  "
                f"Dir={eval_result['direction_accuracy']:.1%}  {bar}",
                flush=True,
            )

        elapsed = time.perf_counter() - t0
        overall_brier = total_brier / total if total else float("inf")
        overall_logl = total_logl / total if total else float("inf")
        overall_dir = correct / total if total else 0.0

        print(
            f"  -> Brier={overall_brier:.4f}  LogLoss={overall_logl:.4f}  "
            f"Dir={overall_dir:.1%}  ({elapsed:.1f}s)",
            flush=True,
        )

        results.append({
            "half_life_days": hl,
            "overall": {
                "brier_score": overall_brier,
                "log_loss": overall_logl,
                "direction_accuracy": overall_dir,
                "direction_counts": {"correct": correct, "wrong": total - correct},
            },
            "n_matches_evaluated": total,
            "walk_forward_fits": len(unique_dates),
            "fit_time_s": round(elapsed, 1),
            "details": all_details,
        })

    return results


# ═══════════════════════════════════════════════════════════════════════
#  Output formatting
# ═══════════════════════════════════════════════════════════════════════

def print_results_table(
    results: list[dict[str, Any]],
    phase: str,
) -> None:
    """Print formatted results table."""
    print(f"\n{'='*80}")
    print(f"  DC Half-Life Grid Search Results -- {phase.upper()} PHASE")
    print(f"{'='*80}")

    # Sort by Brier (lower is better)
    sorted_results = sorted(results, key=lambda r: r["overall"]["brier_score"])

    header = (
        f"{'Rank':<5} {'HL(d)':<8} {'Brier':<8} {'LogLoss':<8} "
        f"{'DirAcc':<8} {'Fit(s)':<8} {'Converged':<10}"
    )
    print(header)
    print("-" * len(header))

    for rank, r in enumerate(sorted_results, 1):
        o = r["overall"]
        conv = "Y" if r.get("fit_converged", True) else "N"
        print(
            f"{rank:<5} {r['half_life_days']:<8} "
            f"{o['brier_score']:<8.4f} {o['log_loss']:<8.4f} "
            f"{o['direction_accuracy']:<8.1%} {r.get('fit_time_s', 0):<8.1f} "
            f"{conv:<10}"
        )

    best = sorted_results[0]
    current_hl = next((r for r in results if r["half_life_days"] == 180), None)
    print(f"\n  Best:  half_life={best['half_life_days']}d  "
          f"Brier={best['overall']['brier_score']:.4f}")
    if current_hl:
        current_rank = next(
            i + 1 for i, r in enumerate(sorted_results)
            if r["half_life_days"] == 180
        )
        delta_brier = current_hl["overall"]["brier_score"] - best["overall"]["brier_score"]
        print(f"  Current (180d): rank={current_rank}  "
              f"dBrier={'+' if delta_brier > 0 else ''}{delta_brier:.4f} "
              f"({'worse' if delta_brier > 0 else 'better'})")

    # Per-stage breakdown for best
    if "group_stage" in best and best["group_stage"]:
        gs = best["group_stage"]
        print(f"\n  Best group-stage:  Brier={gs['brier_score']:.4f}  "
              f"LogLoss={gs['log_loss']:.4f}  Dir={gs['direction_accuracy']:.1%}")
    if "knockout" in best and best["knockout"]:
        ko = best["knockout"]
        print(f"  Best knockout:     Brier={ko['brier_score']:.4f}  "
              f"LogLoss={ko['log_loss']:.4f}  Dir={ko['direction_accuracy']:.1%}")

    print(f"\n{'='*80}")


def save_config(results: list[dict[str, Any]], phase: str) -> None:
    """Save best half-life to dc_params.json config file."""
    sorted_results = sorted(results, key=lambda r: r["overall"]["brier_score"])
    best = sorted_results[0]

    # Build a ranked list of all candidates
    ranking = [
        {
            "rank": i + 1,
            "half_life_days": r["half_life_days"],
            "brier_score": r["overall"]["brier_score"],
            "log_loss": r["overall"]["log_loss"],
            "direction_accuracy": r["overall"]["direction_accuracy"],
        }
        for i, r in enumerate(sorted_results)
    ]

    config = {
        "_description": "DC model time-decay half-life — learned via walk-forward grid search on WC26 matches",
        "_generated_at": datetime.now(timezone.utc).isoformat(),
        "_phase": phase,
        "half_life_days": best["half_life_days"],
        "brier_score": best["overall"]["brier_score"],
        "log_loss": best["overall"]["log_loss"],
        "direction_accuracy": best["overall"]["direction_accuracy"],
        "previous_default": 180,
        "ranking": ranking,
    }

    # Per-competition-type breakdown if available
    if "group_stage" in best and best["group_stage"]:
        config["per_stage"] = {
            "group": {
                "half_life_days": best["half_life_days"],
                "brier_score": best["group_stage"]["brier_score"],
                "log_loss": best["group_stage"]["log_loss"],
                "direction_accuracy": best["group_stage"]["direction_accuracy"],
            }
        }
    if "knockout" in best and best["knockout"]:
        if "per_stage" not in config:
            config["per_stage"] = {}
        config["per_stage"]["knockout"] = {
            "half_life_days": best["half_life_days"],
            "brier_score": best["knockout"]["brier_score"],
            "log_loss": best["knockout"]["log_loss"],
            "direction_accuracy": best["knockout"]["direction_accuracy"],
        }

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n  Config saved to: {CONFIG_PATH}")


def save_full_results(
    coarse_results: list[dict] | None,
    fine_results: list[dict] | None,
) -> None:
    """Save full grid search results as JSON for later analysis."""
    output_path = CONFIG_DIR / "dc_halflife_grid_results.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coarse": coarse_results,
        "fine": fine_results,
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  Full results saved to: {output_path}")


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Grid search DC half-life on WC26 walk-forward CV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--phase",
        choices=["coarse", "fine", "both"],
        default="both",
        help="Which phase to run (default: both)",
    )
    parser.add_argument(
        "--halflife",
        type=str,
        default=None,
        help="Comma-separated half-life values for fine phase (e.g. 60,90,120,180)",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Skip fine phase (coarse only, for quick check)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  DC Half-Life Grid Search")
    print("  Dixon-Coles time-decay parameter optimisation")
    print("=" * 60)

    # -- Load data --
    print("\n-- Loading data --")
    train_df = load_all_training_data()
    eval_df = load_wc26_eval_matches()

    coarse_results: list[dict] | None = None
    fine_results: list[dict] | None = None

    # -- Phase 1: Coarse grid --
    if args.phase in ("coarse", "both"):
        print(f"\n-- Phase 1: Coarse Grid ({len(COARSE_HALF_LIVES)} values) --")
        coarse_results = run_coarse_grid(train_df, eval_df, COARSE_HALF_LIVES)
        print_results_table(coarse_results, "coarse")

        if args.quick:
            save_config(coarse_results, "coarse")
            return

    # ── Phase 2: Fine walk-forward ──
    if args.phase in ("fine", "both"):
        # Determine which half-lives to walk-forward
        if args.halflife:
            fine_candidates = [int(x.strip()) for x in args.halflife.split(",")]
        elif coarse_results:
            # Pick top N from coarse + always include 180 as baseline
            sorted_coarse = sorted(
                coarse_results, key=lambda r: r["overall"]["brier_score"]
            )
            top_ids = {r["half_life_days"] for r in sorted_coarse[:FINE_CANDIDATE_COUNT]}
            top_ids.add(180)  # always include baseline
            fine_candidates = sorted(top_ids)
        else:
            fine_candidates = COARSE_HALF_LIVES

        print(f"\n-- Phase 2: Walk-Forward CV ({len(fine_candidates)} candidates) --")
        print(f"  Candidates: {fine_candidates}")
        fine_results = run_walk_forward(train_df, eval_df, fine_candidates)
        print_results_table(fine_results, "fine")

    # -- Save outputs --
    print("\n-- Saving --")
    primary = fine_results if fine_results else coarse_results
    if primary:
        save_config(primary, "fine" if fine_results else "coarse")
    save_full_results(coarse_results, fine_results)

    print("\nDone.")


if __name__ == "__main__":
    main()

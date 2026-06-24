#!/usr/bin/env python3
"""simulate_wc26.py — WC26 Predict full-tournament Monte Carlo simulation CLI.

Loads trained artifacts from backend/artifacts/, predicts all 72 group-stage
matches, then runs the TournamentSimulator with the specified number of
simulations.

Usage:
    python scripts/simulate_wc26.py --runs 10000 --mode standard
    python scripts/simulate_wc26.py --runs 50000 --mode full --save results.json
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
import time
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import numpy as np
import pandas as pd

from app.services.artifact_registry import load_registry, validate_bundle
from app.services.dixon_coles import DixonColesModel
from app.services.tournament_simulator import TournamentSimulator
from app.services.elo_ratings import EloRatingSystem, fuse_elo_probabilities
from app.services.pi_ratings import PiRatingWrapper, fuse_pi_probabilities
from app.services.tabular_match_model import (
    TabularMatchEnhancer,
    fuse_outcome_probabilities,
)
from app.services.weights import get_weight_config
from app.services.weibull_model import WeibullWrapper, fuse_weibull_probs
from app.services.market.sync_provider import fetch_market_consensus_sync

# ── Constants ──────────────────────────────────────────────────────────

ARTIFACTS_DIR = BACKEND_DIR / "artifacts"
MODELS_DIR = ARTIFACTS_DIR / "models"
RATINGS_DIR = ARTIFACTS_DIR / "ratings"
DATAFRAMES_DIR = ARTIFACTS_DIR / "dataframes"
DB_PATH = BACKEND_DIR / "data" / "local_stage2.db"

ELO_PATH = RATINGS_DIR / "elo.json"
PI_PATH = RATINGS_DIR / "pi.json"
DF_PATH = DATAFRAMES_DIR / "national_finished_matches.pkl"

MODE_REQUIRED_COMPONENTS = {
    "baseline": ["dixon_coles"],
    "standard": ["dixon_coles", "tabular_enhancer", "elo"],
    "full": ["dixon_coles", "tabular_enhancer", "elo", "pi_rating"],
}

GROUPS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]
GROUP_SLOTS = [(1, 2), (3, 4), (1, 3), (2, 4), (1, 4), (2, 3)]


# ── Model loaders (disk cache only — no static artifacts) ──────────────


def load_dc() -> DixonColesModel:
    """Load DC from disk cache (single source of truth since V3.8.0)."""
    from app.services.prediction_core import _load_dc as _load_dc_from_cache
    from app.services.prediction_timer import PredictionTimer
    return _load_dc_from_cache(PredictionTimer())


def load_enhancer() -> TabularMatchEnhancer:
    """Load Enhancer from disk cache (single source of truth since V3.8.0)."""
    from app.services.prediction_core import _load_enhancer as _load_enh_from_cache
    from app.services.prediction_timer import PredictionTimer
    return _load_enh_from_cache(PredictionTimer())


def load_elo() -> EloRatingSystem:
    if not ELO_PATH.exists():
        raise FileNotFoundError(f"Elo artifact not found at {ELO_PATH}")
    elo_data = json.loads(ELO_PATH.read_text("utf-8"))
    elo = EloRatingSystem()
    elo.ratings = {str(k): float(v) for k, v in elo_data.items()}
    return elo


def load_pi() -> PiRatingWrapper:
    if not PI_PATH.exists():
        raise FileNotFoundError(f"Pi-Rating artifact not found at {PI_PATH}")
    pi_data = json.loads(PI_PATH.read_text("utf-8"))
    pi_model = PiRatingWrapper()
    pi_model.team_ratings = {str(k): float(v) for k, v in pi_data.items()}
    return pi_model


def load_weibull(training_df: pd.DataFrame) -> WeibullWrapper | None:
    """Fit Weibull once for reuse across all 72 match predictions.
    Returns None if fitting fails — simulation continues without Weibull.
    """
    try:
        wb = WeibullWrapper()
        if wb.fit(training_df):
            return wb
    except Exception:
        pass
    return None


def load_training_df() -> pd.DataFrame:
    if DF_PATH.exists():
        return pd.read_pickle(str(DF_PATH))
    # Fallback: SQLite
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    df = pd.read_sql_query(
        """
        SELECT ht.name AS home_team, at.name AS away_team,
               mr.home_goals, mr.away_goals, m.match_date,
               COALESCE(m.competition_weight, 1.0) AS competition_weight,
               COALESCE(m.is_neutral_venue, 0) AS is_neutral_venue
        FROM matches m
        JOIN teams ht ON m.home_team_id = ht.id
        JOIN teams at ON m.away_team_id = at.id
        JOIN match_results mr ON m.id = mr.match_id
        WHERE m.competition_type = 'national' AND m.status = 'finished'
          AND m.match_date >= '2018-01-01'
        ORDER BY m.match_date
        """,
        conn,
    )
    conn.close()
    return df


# ── Group-team loading ─────────────────────────────────────────────────


def load_group_teams() -> dict[str, list[str]]:
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    groups: dict[str, list[str]] = {}
    for g in GROUPS:
        rows = conn.execute(
            "SELECT team_name FROM wc26_groups "
            "WHERE group_name = ? ORDER BY slot",
            (g,),
        ).fetchall()
        teams = [r[0] for r in rows if r[0] is not None]
        if teams:
            groups[g] = teams
    conn.close()
    return groups


# ── Match prediction ───────────────────────────────────────────────────


def predict_group_match(
    dc: DixonColesModel,
    enhancer: TabularMatchEnhancer | None,
    elo: EloRatingSystem | None,
    pi_model: PiRatingWrapper | None,
    weibull: WeibullWrapper | None,
    training_df: pd.DataFrame,
    home: str,
    away: str,
    mode: str,
    weight_config: Any,
) -> dict[str, float]:
    """Predict 3-way probabilities for a single group match."""
    is_neutral = True

    # Step 1: Dixon-Coles
    dc_pred = dc.predict_match(home, away, is_neutral_venue=is_neutral)
    fused = {
        "home_win_prob": dc_pred["home_win_prob"],
        "draw_prob": dc_pred["draw_prob"],
        "away_win_prob": dc_pred["away_win_prob"],
    }

    # Step 2: TabularMatchEnhancer (standard+)
    if mode in ("standard", "full") and enhancer is not None:
        match_date = training_df["match_date"].max()
        enh_pred = enhancer.predict_match(
            home_team=home, away_team=away, match_date=match_date,
            competition_weight=1.0, is_neutral_venue=is_neutral,
            training_df=training_df,
        )
        fused = fuse_outcome_probabilities(fused, enh_pred, base_weight=weight_config.dc)

    # Step 2.5: Weibull (standard+, applied after Enhancer for consistency)
    # V4.0.3-fix: Weibull was missing from tournament simulation pipeline.
    if mode in ("standard", "full") and weibull is not None and weibull._fitted:
        wb_pred = weibull.predict(home, away, is_neutral)
        if wb_pred is not None:
            fused = fuse_weibull_probs(fused, wb_pred, wb_weight=weight_config.weibull)

    # Step 3: Elo (standard+)
    if mode in ("standard", "full") and elo is not None:
        elo_pred = elo.predict(
            home, away, is_neutral=is_neutral,
            competition_weight=1.0, competition="FIFA World Cup 2026",
        )
        fused = fuse_elo_probabilities(fused, elo_pred, elo_weight=weight_config.elo)

    # Step 4: Pi-Rating (full)
    if mode == "full" and pi_model is not None:
        try:
            pi_pred = pi_model.predict(home, away, is_neutral)
            fused = fuse_pi_probabilities(fused, pi_pred, pi_weight=weight_config.pi)
        except Exception:
            pass

    # Step 5: Market consensus (R5-5: was missing from tournament simulators)
    try:
        market_raw = fetch_market_consensus_sync(
            home, away, "FIFA World Cup 2026", timeout=8.0,
        )
        if market_raw and not market_raw.get("degraded"):
            market_home = market_raw["home_prob"]
            market_draw = market_raw["draw_prob"]
            market_away = market_raw["away_prob"]
            model_market_div = max(
                abs(fused["home_win_prob"] - market_home),
                abs(fused["draw_prob"] - market_draw),
                abs(fused["away_win_prob"] - market_away),
            )
            market_weight = weight_config.market_max
            if model_market_div > 0.15:
                boost = min(0.20, (model_market_div - 0.15) * 1.0)
                market_weight = min(0.50, weight_config.market_max + boost)
            fused_market = {
                "home_win_prob": fused["home_win_prob"] * (1 - market_weight) + market_home * market_weight,
                "draw_prob": fused["draw_prob"] * (1 - market_weight) + market_draw * market_weight,
                "away_win_prob": fused["away_win_prob"] * (1 - market_weight) + market_away * market_weight,
            }
            total_m = sum(fused_market.values())
            fused = {k: v / total_m for k, v in fused_market.items()}
    except Exception:
        pass  # Market is best-effort

    return fused


# ── Main ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="WC26 Monte Carlo Tournament Simulation"
    )
    parser.add_argument(
        "--runs", type=int, default=10_000,
        help="Number of Monte Carlo simulations (default: 10,000)",
    )
    parser.add_argument(
        "--mode", type=str, default="standard",
        choices=["baseline", "standard", "full"],
        help="Prediction mode: baseline (DC only), standard (DC+Enhancer+Elo), "
             "full (DC+Enhancer+Elo+Pi)",
    )
    parser.add_argument(
        "--save", type=str, default=None,
        help="Path to save JSON results (default: reports/wc26_simulation.json)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    args = parser.parse_args()

    t_start = time.perf_counter()
    print(f"{'='*70}")
    print(f"  WC26 Tournament Simulation")
    print(f"  Runs: {args.runs:,}  |  Mode: {args.mode}")
    print(f"{'='*70}")

    # 1. Validate artifact registry
    print("\n[1] Validating artifact registry...")
    registry = load_registry()
    ok, missing = validate_bundle(registry, args.mode)
    if not ok:
        print(f"  ERROR: Missing required artifacts: {missing}")
        print("  Run: python scripts/train_models.py")
        sys.exit(1)
    print(f"  Registry OK ({args.mode} mode)")

    # 2. Load all artifacts
    print("\n[2] Loading artifacts...")
    dc = load_dc()
    print(f"  DC model loaded: {len(dc.attack_params)} teams rated")

    enhancer = load_enhancer() if args.mode in ("standard", "full") else None
    if enhancer:
        print(f"  TabularMatchEnhancer loaded (fitted={enhancer.is_fitted})")

    elo = load_elo() if args.mode in ("standard", "full") else None
    if elo is not None:
        print(f"  Elo ratings loaded: {len(elo.ratings)} teams")

    pi_model = load_pi() if args.mode == "full" else None
    if pi_model is not None:
        print(f"  Pi-Ratings loaded: {len(pi_model.team_ratings)} teams")

    training_df = load_training_df()
    print(f"  Training data loaded: {len(training_df)} matches")

    # 2.5. Load Weibull (fit once for all matches, best-effort)
    weibull = load_weibull(training_df) if args.mode in ("standard", "full") else None
    if weibull and weibull._fitted:
        print(f"  Weibull fitted OK")
    else:
        print(f"  Weibull: unavailable (continuing without)")

    # 3. Load weight config
    weight_config = get_weight_config("FIFA World Cup 2026", "Group Stage")
    print(f"  Weights: DC={weight_config.dc:.2f}  Enh={weight_config.enhancer:.2f}  "
          f"Wb={weight_config.weibull:.2f}  Elo={weight_config.elo:.2f}  Pi={weight_config.pi:.2f}")

    # 4. Load group teams
    print("\n[3] Loading group assignments...")
    groups = load_group_teams()
    all_teams: set[str] = set()
    for g, teams in groups.items():
        all_teams.update(teams)
        print(f"  Group {g}: {', '.join(teams)}")
    print(f"  Total teams: {len(all_teams)}")

    # 5. Predict all 72 group matches
    print(f"\n[4] Predicting 72 group-stage matches...")
    match_probs: dict[tuple[str, str], dict[str, float]] = {}
    predicted_count = 0
    for g in GROUPS:
        if g not in groups:
            continue
        teams = groups[g]
        for home_slot, away_slot in GROUP_SLOTS:
            home = teams[home_slot - 1]
            away = teams[away_slot - 1]
            try:
                probs = predict_group_match(
                    dc, enhancer, elo, pi_model, weibull,
                    training_df, home, away, args.mode, weight_config,
                )
                match_probs[(home, away)] = probs
                predicted_count += 1
                if predicted_count <= 6 or predicted_count % 12 == 0:
                    print(f"  {home} vs {away}: H={probs['home_win_prob']:.3f} "
                          f"D={probs['draw_prob']:.3f} A={probs['away_win_prob']:.3f}")
            except Exception as e:
                print(f"  WARNING: Failed to predict {home} vs {away}: {e}")
                match_probs[(home, away)] = {
                    "home_win_prob": 0.40, "draw_prob": 0.30, "away_win_prob": 0.30,
                }
                predicted_count += 1
    print(f"  Predicted {predicted_count} matches")

    # 6. Build and run simulator
    print(f"\n[5] Running TournamentSimulator ({args.runs:,} runs)...")
    sim = TournamentSimulator(runs=args.runs, seed=args.seed)
    sim.load_schedule(str(DB_PATH))

    for (home, away), probs in match_probs.items():
        sim.set_match_probability(home, away, {
            "home_win": probs["home_win_prob"],
            "draw": probs["draw_prob"],
            "away_win": probs["away_win_prob"],
        })

    results = sim.run()

    # 7. Print summary
    print(f"\n{sim.summary()}")

    # 8. Save results
    save_path = args.save
    if save_path is None:
        save_path = str(BACKEND_DIR / "reports" / "wc26_simulation.json")
    sim.save_json(save_path)

    t_elapsed = time.perf_counter() - t_start
    print(f"\nDone in {t_elapsed:.1f}s. Results saved to {save_path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""RPS-driven weight optimization for model ensemble.

Reads postmatch_eval, computes optimal per-component weights via Nelder-Mead
optimization of Ranked Probability Score (RPS).

RPS respects ordinal nature of football outcomes (H > D > A) better than Brier.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

BACKEND_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BACKEND_DIR / "data" / "local_stage2.db"

COMPONENTS = ["dc", "enhancer", "elo", "pi_rating"]


def ranked_probability_score(pred, actual):
    """RPS = mean((cum_pred - cum_actual)^2) for 3 outcomes."""
    cp = np.cumsum(pred[:3])
    ca = np.cumsum([1.0 if i == actual else 0.0 for i in range(3)])
    return float(np.mean((cp - ca) ** 2))


def load_data():
    """Load predictions with component-level probabilities."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Join: prediction_runs->postmatch_eval (+ stages from matches)
    rows = conn.execute("""
        SELECT pr.home_win_prob, pr.draw_prob, pr.away_win_prob,
               pe.actual_result, m.competition, m.stage,
               ps.component_probs
        FROM prediction_runs pr
        JOIN postmatch_eval pe ON pe.prediction_run_id = pr.id
        JOIN matches m ON pr.match_id = m.id
        LEFT JOIN prediction_snapshots ps ON ps.match_id = m.id
        WHERE pe.actual_result IN ('H', 'D', 'A')
        ORDER BY pe.created_at DESC
        LIMIT 200
    """).fetchall()
    conn.close()

    actual_map = {"H": 0, "D": 1, "A": 2}
    data = []
    for r in rows:
        actual = actual_map.get(r["actual_result"])
        if actual is None:
            continue

        # Parse component probs from snapshot (may be NULL)
        comp = _parse_comp_probs(r["component_probs"])
        if not comp:
            # Fallback: estimate from final probs
            comp = {
                "dc": [r["home_win_prob"] * 0.6, r["draw_prob"] * 0.6, r["away_win_prob"] * 0.6],
                "enhancer": [r["home_win_prob"] * 0.3, r["draw_prob"] * 0.3, r["away_win_prob"] * 0.3],
                "elo": [r["home_win_prob"] * 0.05, r["draw_prob"] * 0.05, r["away_win_prob"] * 0.05],
                "pi_rating": [r["home_win_prob"] * 0.05, r["draw_prob"] * 0.05, r["away_win_prob"] * 0.05],
            }

        data.append({
            "dc": comp.get("dc", [0.33, 0.34, 0.33]),
            "enhancer": comp.get("enhancer", [0.33, 0.34, 0.33]),
            "elo": comp.get("elo", [0.33, 0.34, 0.33]),
            "pi_rating": comp.get("pi_rating", [0.33, 0.34, 0.33]),
            "final": [r["home_win_prob"] or 0.33, r["draw_prob"] or 0.34, r["away_win_prob"] or 0.33],
            "actual": actual,
            "stage": r["stage"] or "",
        })

    return data


def _parse_comp_probs(raw):
    """Parse component_probs JSON from database."""
    if not raw:
        return None
    try:
        if isinstance(raw, str):
            return json.loads(raw)
        return dict(raw)
    except Exception:
        return None


def optimize_weights(data):
    """Find optimal weights via Nelder-Mead."""
    if len(data) < 10:
        print(f"Only {len(data)} records, need >=10. Using defaults.")
        return {"dc": 0.50, "enhancer": 0.30, "elo": 0.05, "pi_rating": 0.05}

    def ensemble_rps(w):
        w_abs = np.abs(w) / np.sum(np.abs(w))
        total = 0.0
        for d in data:
            blended = np.zeros(3)
            for i, comp in enumerate(COMPONENTS):
                arr = np.array(d[comp][:3])
                blended += w_abs[i] * (arr / arr.sum())
            total += ranked_probability_score(blended.tolist(), d["actual"])
        return total / len(data)

    x0 = np.array([0.50, 0.30, 0.05, 0.05])
    current_rps = ensemble_rps(x0)

    result = minimize(ensemble_rps, x0, method="Nelder-Mead",
                       options={"maxiter": 500, "xatol": 1e-4})

    optimal = np.abs(result.x) / np.sum(np.abs(result.x))
    weights = {comp: float(optimal[i]) for i, comp in enumerate(COMPONENTS)}
    optimal_rps = ensemble_rps(optimal)

    print(f"Records: {len(data)}")
    print(f"Current RPS: {current_rps:.4f} (DC{x0[0]:.0%} Enh{x0[1]:.0%} Elo{x0[2]:.0%} Pi{x0[3]:.0%})")
    print(f"Optimal:      {optimal_rps:.4f} (DC{weights['dc']:.0%} Enh{weights['enhancer']:.0%} Elo{weights['elo']:.0%} Pi{weights['pi_rating']:.0%})")
    if current_rps > 0:
        print(f"Improvement:  {(current_rps - optimal_rps) / current_rps * 100:.1f}%")
    return weights


def save_weights(weights, label="auto_optimized"):
    """Write to model_weight_config."""
    conn = sqlite3.connect(str(DB_PATH))
    for comp in COMPONENTS:
        key = f"{label}_{comp}"
        conn.execute("""INSERT OR REPLACE INTO model_weight_config
            (config_key, config_value, previous_value, updated_at, update_reason, updated_by)
            VALUES (?, ?, (SELECT config_value FROM model_weight_config WHERE config_key=?), datetime('now'), 'RPS auto-optimize', 'optimize_weights.py')""",
            (key, str(round(weights[comp], 4)), key))
    conn.commit()
    conn.close()
    print("Weights saved.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    print("Loading historical predictions...")
    data = load_data()
    print(f"Loaded {len(data)} records.")

    weights = optimize_weights(data)

    if args.dry_run:
        print("\n[Dry run] Not saved.")
    else:
        save_weights(weights)


if __name__ == "__main__":
    main()

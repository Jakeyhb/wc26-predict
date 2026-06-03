"""Phase 2: Backtest market calibrator — compare BaseOnly vs MarketOnly vs FinalBlend.

Uses historical post-match evaluation data to determine if market consensus
calibration improves prediction accuracy.

Metrics: Brier Score, LogLoss, RPS, ECE

Shadow mode rule: If FinalBlend does NOT consistently beat BaseOnly in rolling
backtest, market calibration stays in shadow mode (does NOT go to production).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import numpy as np


def brier_score(probs: dict[str, float], actual: int) -> float:
    """Brier score for a 3-outcome prediction.

    Args:
        probs: {home_win_prob, draw_prob, away_win_prob}
        actual: 0=home, 1=draw, 2=away
    """
    outcomes = np.array([probs["home_win_prob"], probs["draw_prob"], probs["away_win_prob"]])
    actual_vec = np.zeros(3)
    actual_vec[actual] = 1.0
    return float(np.sum((outcomes - actual_vec) ** 2))


def log_loss(probs: dict[str, float], actual: int, eps: float = 1e-12) -> float:
    """Log loss (cross-entropy) for a 3-outcome prediction."""
    p = np.array([probs["home_win_prob"], probs["draw_prob"], probs["away_win_prob"]])
    p = np.clip(p, eps, 1.0 - eps)
    p = p / p.sum()
    return float(-np.log(p[actual]))


def rps(probs: dict[str, float], actual: int) -> float:
    """Ranked Probability Score for ordinal 3-outcome."""
    outcomes = np.array([probs["home_win_prob"], probs["draw_prob"], probs["away_win_prob"]])
    actual_vec = np.zeros(3)
    actual_vec[actual] = 1.0
    cum_probs = np.cumsum(outcomes)
    cum_actual = np.cumsum(actual_vec)
    return float(np.mean((cum_probs - cum_actual) ** 2))


def ece(prob_list: list[float], actual_list: list[int], n_bins: int = 10) -> float:
    """Expected Calibration Error."""
    if len(prob_list) < n_bins:
        return float("nan")
    prob_arr = np.array(prob_list)
    actual_arr = np.array(actual_list)
    bins = np.linspace(0, 1, n_bins + 1)
    ece_sum = 0.0
    for i in range(n_bins):
        mask = (prob_arr >= bins[i]) & (prob_arr < bins[i + 1])
        if mask.sum() == 0:
            continue
        bin_acc = actual_arr[mask].mean()
        bin_conf = prob_arr[mask].mean()
        ece_sum += mask.sum() * abs(bin_acc - bin_conf)
    return float(ece_sum / len(prob_list))


def main():
    print("=" * 60)
    print("Market Calibrator Backtest (Shadow Mode)")
    print(f"Run: {datetime.now().isoformat()}")
    print("=" * 60)

    # 1. Load post-match evaluation data
    print("\n1. Loading post-match evaluation data...")
    try:
        import sqlite3
        db = PROJECT_ROOT / "data" / "local_stage2.db"
        conn = sqlite3.connect(str(db))
        c = conn.cursor()

        # Get evaluations linked to prediction snapshots
        c.execute("""
            SELECT pe.actual_home_goals, pe.actual_away_goals,
                   pe.brier_score, pe.log_loss,
                   ps.baseline_probs, ps.market_probs, ps.adjusted_probs,
                   ps.home_team, ps.away_team
            FROM postmatch_eval pe
            JOIN prediction_snapshots ps ON pe.prediction_run_id = ps.id
            WHERE ps.market_probs IS NOT NULL
            LIMIT 50
        """)
        rows = c.fetchall()
        print(f"   Found {len(rows)} evaluations with market data")
        conn.close()
    except Exception as e:
        print(f"   DB error: {e}")
        rows = []

    if len(rows) < 5:
        print("\n2. INSUFFICIENT DATA for backtest")
        print(f"   Need >= 5 evaluations with market data, got {len(rows)}")
        print("   Market calibration remains in SHADOW MODE")
        print("\n   Next steps:")
        print("   1. Run snapshot.py with --shadow to accumulate market snapshots")
        print("   2. After each WC26 match, run auto_postmatch.py to record results")
        print("   3. Re-run this backtest after accumulating 10+ evaluations")
        print("   4. If FinalBlend consistently beats BaseOnly, enable active mode")
        return

    # 2. Compute metrics for each strategy
    print("\n2. Computing metrics...")
    import json

    base_scores = {"brier": [], "logloss": [], "rps": [], "ece": []}
    market_scores = {"brier": [], "logloss": [], "rps": [], "ece": []}

    for row in rows:
        home_goals = int(row[0])
        away_goals = int(row[1])
        if home_goals > away_goals:
            actual = 0
        elif home_goals == away_goals:
            actual = 1
        else:
            actual = 2

        # BaseOnly: baseline_probs
        try:
            base_probs = json.loads(row[4]) if row[4] else {}
            if base_probs:
                base_scores["brier"].append(brier_score(base_probs, actual))
                base_scores["logloss"].append(log_loss(base_probs, actual))
                base_scores["rps"].append(rps(base_probs, actual))
        except (json.JSONDecodeError, KeyError):
            pass

        # MarketOnly: market_probs
        try:
            market_probs = json.loads(row[5]) if row[5] else {}
            if market_probs and "home_win_prob" in market_probs:
                market_scores["brier"].append(brier_score(market_probs, actual))
                market_scores["logloss"].append(log_loss(market_probs, actual))
                market_scores["rps"].append(rps(market_probs, actual))
        except (json.JSONDecodeError, KeyError):
            pass

    # 3. Summary
    print(f"\n3. Results ({len(base_scores['brier'])} base, {len(market_scores['brier'])} market):")
    print(f"   {'Metric':<12} {'BaseOnly':>10} {'MarketOnly':>10} {'Δ':>10}")
    print(f"   {'-'*42}")

    verdicts = []
    for metric in ["brier", "logloss", "rps"]:
        b_vals = base_scores[metric]
        m_vals = market_scores[metric]
        if b_vals and m_vals:
            b_mean = np.mean(b_vals)
            m_mean = np.mean(m_vals)
            diff = b_mean - m_mean  # positive = base better (lower is better)
            direction = "Base wins" if diff < 0 else "Market wins"
            print(f"   {metric:<12} {b_mean:>10.4f} {m_mean:>10.4f} {diff:>+10.4f}  {direction}")
            verdicts.append(diff)
        elif b_vals:
            print(f"   {metric:<12} {np.mean(b_vals):>10.4f} {'N/A':>10} {'N/A':>10}")
        else:
            print(f"   {metric:<12} {'N/A':>10} {'N/A':>10} {'N/A':>10}")

    # 4. Decision
    print(f"\n4. Shadow Mode Decision:")
    if len(verdicts) < 3:
        print("   INCONCLUSIVE — insufficient data for all metrics")
        print("   Market calibration STAYS in shadow mode")
    elif all(v < 0 for v in verdicts):
        print("   PASS — BaseOnly is better on all metrics")
        print("   Market calibration STAYS in shadow mode (market not adding value)")
    elif all(v > 0 for v in verdicts):
        print("   CANDIDATE — MarketOnly is better on all metrics")
        print("   Consider enabling active mode after 20+ more evaluations")
    else:
        print("   MIXED — market helps some metrics, hurts others")
        print("   Market calibration STAYS in shadow mode until consistent improvement")

    print(f"\n   Reference: action plan threshold:")
    print(f"     rolling_30: FinalBlend Brier <= BaseOnly Brier - 0.005")
    print(f"     rolling_30: FinalBlend LogLoss <= BaseOnly LogLoss")
    print(f"     no severe calibration regression")

    # 5. Market data coverage report
    print(f"\n5. Market Data Coverage:")
    try:
        conn = sqlite3.connect(str(db))
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM market_odds")
        odds_total = c.fetchone()[0]
        c.execute("SELECT COUNT(DISTINCT match_id) FROM market_odds WHERE match_id IS NOT NULL")
        odds_unique = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM market_consensus_snapshots")
        consensus_total = c.fetchone()[0]
        print(f"   market_odds records: {odds_total} ({odds_unique} unique matches)")
        print(f"   market_consensus_snapshots: {consensus_total}")
        conn.close()
    except Exception:
        pass

    print(f"\n{'=' * 60}")
    print("Backtest complete. Market calibration in SHADOW MODE.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()

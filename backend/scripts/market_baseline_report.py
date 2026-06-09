"""market_baseline_report.py — Compare model predictions against market implied odds.

Reads pre_match_snapshots with odds_available=True and compares the model's
final probabilities against the market's implied probabilities (after vig
removal). Produces a summary table showing which side the model leans toward.

Usage:
    python scripts/market_baseline_report.py              # all snapshots
    python scripts/market_baseline_report.py --limit 20   # last 20
    python scripts/market_baseline_report.py --team "France"  # filter by team
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BACKEND_DIR / "data" / "local_stage2.db"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Market baseline comparison report"
    )
    parser.add_argument("--limit", type=int, default=50, help="Max rows to show")
    parser.add_argument("--team", help="Filter by team name")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"DB not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Query: find pre_match_snapshots with odds data that have consensus in market_consensus_snapshots
    query = """
        SELECT
            ps.home_team, ps.away_team, ps.competition, ps.snapshot_at,
            ps.final_home_prob, ps.final_draw_prob, ps.final_away_prob,
            ps.odds_snapshot,
            mcs.consensus_home, mcs.consensus_draw, mcs.consensus_away,
            mcs.provider_count, mcs.overround_avg, mcs.confidence,
            mcs.provider_names
        FROM pre_match_snapshots ps
        LEFT JOIN market_consensus_snapshots mcs
            ON (mcs.home_team = ps.home_team AND mcs.away_team = ps.away_team)
        WHERE ps.odds_available = 1
          AND mcs.consensus_home IS NOT NULL
        ORDER BY ps.snapshot_at DESC
        LIMIT ?
    """

    params = [args.limit]
    if args.team:
        query = query.replace("ORDER BY", "AND (ps.home_team = ? OR ps.away_team = ?) ORDER BY")
        params = [args.team, args.team, args.limit]

    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        print("No market consensus data found for comparison.")
        return

    print("=" * 100)
    print("MARKET BASELINE COMPARISON REPORT")
    print(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Snapshots with market data: {len(rows)}")
    print("=" * 100)

    total_div = 0.0
    max_div = 0.0
    max_div_match = ""
    model_leaned_home = 0
    model_leaned_away = 0

    print(f"\n{'Match':<35} {'Model':>18} {'Market':>18} {'Div':>7} {'Lean'}")
    print("-" * 100)

    for r in rows:
        div = max(
            abs(r["final_home_prob"] - (r["consensus_home"] or 0)),
            abs(r["final_draw_prob"] - (r["consensus_draw"] or 0)),
            abs(r["final_away_prob"] - (r["consensus_away"] or 0)),
        )
        total_div += div
        if div > max_div:
            max_div = div
            max_div_match = f"{r['home_team']} vs {r['away_team']}"

        # Model lean direction
        model_lean = ""
        if r["final_home_prob"] > (r["consensus_home"] or 0) + 0.02:
            model_lean = "HOME+"
            model_leaned_home += 1
        elif r["final_away_prob"] > (r["consensus_away"] or 0) + 0.02:
            model_lean = "AWAY+"
            model_leaned_away += 1

        match_str = f"{r['home_team']} vs {r['away_team']}"
        model_str = f"{r['final_home_prob']:.1%}/{r['final_draw_prob']:.1%}/{r['final_away_prob']:.1%}"
        market_str = f"{(r['consensus_home'] or 0):.1%}/{(r['consensus_draw'] or 0):.1%}/{(r['consensus_away'] or 0):.1%}"

        print(f"{match_str:<35} {model_str:>18} {market_str:>18} {div:>6.1%}  {model_lean}")

    avg_div = total_div / len(rows) if rows else 0

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"  Total snapshots compared:    {len(rows)}")
    print(f"  Average model-market divergence: {avg_div:.1%}")
    print(f"  Maximum divergence:             {max_div:.1%} ({max_div_match})")
    print(f"  Model leans HOME vs market:   {model_leaned_home}")
    print(f"  Model leans AWAY vs market:   {model_leaned_away}")
    print(f"  Neutral (within 2pp):           {len(rows) - model_leaned_home - model_leaned_away}")
    print()

    if avg_div > 0.12:
        print("  [NOTE] Average divergence >12pp — consider recalibration.")
    if max_div > 0.30:
        print(f"  [WARN] High divergence outlier: {max_div_match} ({max_div:.1%})")

    print("=" * 100)

    # Provider breakdown
    conn2 = sqlite3.connect(str(DB_PATH))
    conn2.row_factory = sqlite3.Row
    prov_rows = conn2.execute(
        """SELECT provider_names, COUNT(*) as n
           FROM market_consensus_snapshots
           WHERE provider_names IS NOT NULL
           GROUP BY provider_names"""
    ).fetchall()
    conn2.close()

    if prov_rows:
        print("\nMarket Data Providers:")
        for pr in prov_rows:
            print(f"  {pr['provider_names']}: {pr['n']} consensus snapshots")


if __name__ == "__main__":
    main()

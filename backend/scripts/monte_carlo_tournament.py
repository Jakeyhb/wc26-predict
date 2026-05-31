#!/usr/bin/env python3
"""Monte Carlo tournament simulation for WC2026 knockout stage.

Simulates the full tournament 100,000 times, outputting each team's
probability of reaching each round and winning the World Cup.

Uses Dixon-Coles model trained on all national team data for match-level
predictions, then simulates poisson draws for each fixture.

Usage:
    python scripts/monte_carlo_tournament.py           # Full sim
    python scripts/monte_carlo_tournament.py --n 10000  # Quick 10K sim
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import poisson

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.dixon_coles import DixonColesModel

# WC2026 knockout bracket structure (Match numbers 73-104)
# Round of 32 matches: winners from each group paired by FIFA bracket
# Simplified: use group winner vs best 3rd, group runner-up vs another group winner

# For the initial implementation, map group positions to R32 match slots
R32_SLOTS = 16  # 32 teams → 16 matches
R16_SLOTS = 8
QF_SLOTS = 4
SF_SLOTS = 2

# Group exit → Round of 32 slot mapping (FIFA official bracket)
# Each tuple: (group_rank, opponent_group, opponent_rank)
# This is a simplified bracket — the actual FIFA bracket has complex rules
# for best 3rd place teams. This approximation captures ~90% of the structure.
R32_MAP = [
    # Match 1-2: Group A vs Group B
    (("A", 1), ("B", 2)),   # A1 vs B2
    (("B", 1), ("A", 2)),   # B1 vs A2
    # Match 3-4: Group C vs Group D
    (("C", 1), ("D", 2)),
    (("D", 1), ("C", 2)),
    # Match 5-6: Group E vs Group F
    (("E", 1), ("F", 2)),
    (("F", 1), ("E", 2)),
    # Match 7-8: Group G vs Group H
    (("G", 1), ("H", 2)),
    (("H", 1), ("G", 2)),
    # Match 9-10: Group I vs Group J
    (("I", 1), ("J", 2)),
    (("J", 1), ("I", 2)),
    # Match 11-12: Group K vs Group L
    (("K", 1), ("L", 2)),
    (("L", 1), ("K", 2)),
    # Match 13-16: Best 4 third-place teams vs group winners
    (("C", 1), ("D", 3)),   # Placeholder — actual depends on which 3rd-place teams advance
    (("E", 1), ("F", 3)),
    (("G", 1), ("H", 3)),
    (("I", 1), ("J", 3)),
]

# Knockout bracket after R32 — pairwise progression
# R32 winner 0 vs winner 1 → R16, etc.
R16_MAP = [(0, 1), (2, 3), (4, 5), (6, 7), (8, 9), (10, 11), (12, 13), (14, 15)]
QF_MAP = [(0, 1), (2, 3), (4, 5), (6, 7)]
SF_MAP = [(0, 1), (2, 3)]


def load_group_teams() -> dict[str, list[str]]:
    """Load WC2026 group assignments from database."""
    import sqlite3
    db = BACKEND_DIR / "data" / "local_stage2.db"
    conn = sqlite3.connect(str(db))
    groups = {}
    for g in "ABCDEFGHIJKL":
        rows = conn.execute(f"""
            SELECT DISTINCT ht.name FROM matches m
            JOIN teams ht ON m.home_team_id = ht.id
            WHERE m.competition = 'FIFA World Cup 2026' AND m.stage LIKE 'Group {g}%'
            UNION
            SELECT DISTINCT at.name FROM matches m
            JOIN teams at ON m.away_team_id = at.id
            WHERE m.competition = 'FIFA World Cup 2026' AND m.stage LIKE 'Group {g}%'
        """).fetchall()
        groups[g] = sorted([r[0] for r in rows])
    conn.close()
    return groups


def simulate_group(dc_model: DixonColesModel, teams: list[str]) -> list[str]:
    """Simulate one group's 6 matches and return teams ranked 1-4 by points.

    Top 2 advance. Tiebreakers: goal difference, then goals scored.
    """
    standings: dict[str, dict] = {t: {"pts": 0, "gd": 0, "gf": 0} for t in teams}

    matchups = [(0, 1), (2, 3), (0, 2), (1, 3), (0, 3), (1, 2)]
    for h_idx, a_idx in matchups:
        home, away = teams[h_idx], teams[a_idx]
        try:
            pred = dc_model.predict(home, away, is_neutral=True)
            lam, mu = pred["home_xg"], pred["away_xg"]
        except Exception:
            lam, mu = 1.2, 1.0

        hg = poisson.rvs(max(0.01, lam))
        ag = poisson.rvs(max(0.01, mu))

        standings[home]["gf"] += hg
        standings[away]["gf"] += ag
        standings[home]["gd"] += hg - ag
        standings[away]["gd"] += ag - hg

        if hg > ag:
            standings[home]["pts"] += 3
        elif ag > hg:
            standings[away]["pts"] += 3
        else:
            standings[home]["pts"] += 1
            standings[away]["pts"] += 1

    ranked = sorted(teams, key=lambda t: (standings[t]["pts"], standings[t]["gd"], standings[t]["gf"]), reverse=True)
    return ranked


def simulate_match(dc_model, home: str, away: str) -> str:
    """Simulate one knockout match. Draw → penalties (50/50)."""
    try:
        pred = dc_model.predict(home, away, is_neutral=True)
        lam, mu = pred["home_xg"], pred["away_xg"]
    except Exception:
        lam, mu = 1.1, 1.0

    hg = poisson.rvs(max(0.01, lam))
    ag = poisson.rvs(max(0.01, mu))
    if hg > ag:
        return home
    if ag > hg:
        return away
    return home if np.random.random() > 0.5 else away


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=100_000, help="Number of simulations")
    args = parser.parse_args()

    N = args.n
    print(f"🏆 WC2026 Monte Carlo Tournament Simulation ({N:,} runs)")
    print("=" * 60)

    # 1. Load teams
    groups = load_group_teams()
    all_teams = set()
    for g, teams in groups.items():
        all_teams.update(teams)
        print(f"  Group {g}: {', '.join(teams[:3])}...")

    # 2. Train Dixon-Coles on national team data
    print("\n📊 Loading national team training data...")
    import sqlite3
    conn = sqlite3.connect(str(BACKEND_DIR / "data" / "local_stage2.db"))
    rows = conn.execute("""
        SELECT ht.name as home_team, at.name as away_team,
               m.match_date, m.competition_weight, m.is_neutral_venue,
               r.home_goals, r.away_goals
        FROM matches m
        JOIN teams ht ON m.home_team_id = ht.id
        JOIN teams at ON m.away_team_id = at.id
        JOIN match_results r ON m.id = r.match_id
        WHERE m.competition_type = 'national' AND m.status = 'finished'
          AND m.match_date >= '2018-01-01'
        ORDER BY m.match_date
    """).fetchall()
    conn.close()
    df = pd.DataFrame(rows, columns=["home_team", "away_team", "match_date", "competition_weight", "is_neutral_venue", "home_goals", "away_goals"])
    print(f"  Training data: {len(df)} matches")
    dc = DixonColesModel()
    dc.fit(df)
    print(f"  Teams rated: {len(dc.attack_params)}")

    # 3. Initialize counters
    results: dict[str, dict[str, int]] = {t: {"R32": 0, "R16": 0, "QF": 0, "SF": 0, "Final": 0, "Champion": 0} for t in all_teams}
    champion_counts: Counter = Counter()

    # 4. Simulate
    print(f"\n🎲 Running {N:,} simulations...")
    for sim in range(N):
        if (sim + 1) % (N // 10) == 0:
            print(f"  {sim + 1:,}/{N:,} ({(sim+1)/N*100:.0f}%)")

        # 4a. Simulate group stages
        group_results: dict[str, list[str]] = {}
        for g, teams in groups.items():
            group_results[g] = simulate_group(dc, teams)

        # 4b. Build R32 bracket
        r32_winners = []
        for (g1, r1), (g2, r2) in R32_MAP:
            t1 = group_results[g1][r1 - 1]  # 0-indexed
            t2 = group_results[g2][r2 - 1]
            winner = simulate_match(dc, t1, t2)
            r32_winners.append(winner)
            for t in [t1, t2]:
                results[t]["R32"] += 1

        # 4c. R16
        r16_winners = []
        for i, j in R16_MAP:
            t1, t2 = r32_winners[i], r32_winners[j]
            winner = simulate_match(dc, t1, t2)
            r16_winners.append(winner)
            for t in [t1, t2]:
                results[t]["R16"] += 1

        # 4d. Quarterfinals
        qf_winners = []
        for i, j in QF_MAP:
            t1, t2 = r16_winners[i], r16_winners[j]
            winner = simulate_match(dc, t1, t2)
            qf_winners.append(winner)
            for t in [t1, t2]:
                results[t]["QF"] += 1

        # 4e. Semifinals
        sf_winners = []
        for i, j in SF_MAP:
            t1, t2 = qf_winners[i], qf_winners[j]
            winner = simulate_match(dc, t1, t2)
            sf_winners.append(winner)
            for t in [t1, t2]:
                results[t]["SF"] += 1

        # 4f. Final
        t1, t2 = sf_winners[0], sf_winners[1]
        champion = simulate_match(dc, t1, t2)
        champion_counts[champion] += 1
        for t in [t1, t2]:
            results[t]["Final"] += 1
        results[champion]["Champion"] += 1

    # 5. Print results
    print(f"\n{'='*60}")
    print("🏆 WC2026 Tournament Probabilities")
    print(f"{'='*60}")
    print(f"{'Team':<25} {'R32':>6} {'R16':>6} {'QF':>6} {'SF':>6} {'Final':>6} {'🏆':>6}")
    print("-" * 73)

    for team, probs in sorted(results.items(), key=lambda x: -x[1]["Champion"]):
        print(f"{team:<25} {probs['R32']/N*100:>5.1f}% {probs['R16']/N*100:>5.1f}% "
              f"{probs['QF']/N*100:>5.1f}% {probs['SF']/N*100:>5.1f}% "
              f"{probs['Final']/N*100:>5.1f}% {probs['Champion']/N*100:>5.1f}%")

    # 6. Save to JSON
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_simulations": N,
        "teams": {t: {k: v / N for k, v in probs.items()} for t, probs in results.items()},
        "champion_probs": {t: c / N for t, c in champion_counts.most_common(20)},
    }
    out_path = BACKEND_DIR / "reports" / "wc26_monte_carlo.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\n📄 Saved to {out_path}")


if __name__ == "__main__":
    main()

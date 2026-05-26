#!/usr/bin/env python3
"""Fast numeric prediction — Dixon-Coles + Enhancer + Elo only.
Target: <3s per match (with cached model parameters).

Current: ~35s with full re-fit. Will approach target once pre-fitted
model parameters are cached and reused.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import AsyncSessionLocal
from app.services.dixon_coles import DixonColesModel, load_training_frame, WC26_FIFA_TIERS
from app.services.elo_ratings import EloRatingSystem, fuse_elo_probabilities
from app.services.tabular_match_model import TabularMatchEnhancer, fuse_outcome_probabilities


async def fast_predict(
    home_team: str,
    away_team: str,
    *,
    competition: str = "Premier League",
    is_neutral: bool = False,
    competition_weight: float = 0.9,
) -> dict:
    """Run numeric prediction layers, return minimal result dict."""

    is_national = any(kw in competition.lower() for kw in ["world cup", "euro", "copa", "nations", "international"])
    comp_type = "national" if is_national else "club"
    team_t = "national" if is_national else "club"

    async with AsyncSessionLocal() as db:
        df = await load_training_frame(db, competition=None if is_national else competition, competition_type=comp_type, team_type=team_t)

        # Build team registry for cold-start fallback
        from app.models.team import Team
        from sqlalchemy import select
        result = await db.execute(select(Team.name, Team.confederation).where(Team.team_type == team_t))
        team_info = {}
        for name, conf in result.all():
            team_info[name] = {"confederation": conf or "FIFA", "fifa_tier": WC26_FIFA_TIERS.get(name, 0)}

    if df.empty:
        raise RuntimeError(f"No training data for {competition}")

    # Layer 1: Dixon-Coles
    dc = DixonColesModel()
    dc.set_team_info(team_info)
    dc_fit = dc.fit(df)
    dc_pred = dc.predict_match(home_team, away_team, is_neutral_venue=is_neutral)

    # Layer 2: Tabular Enhancer
    enhancer = TabularMatchEnhancer()
    enhancer.fit(df)
    enh_pred = enhancer.predict_match(
        home_team=home_team, away_team=away_team,
        match_date=df["match_date"].max().to_pydatetime(),
        competition_weight=competition_weight,
        is_neutral_venue=is_neutral,
        training_df=df, rest_days={"home": 5, "away": 5},
    )

    # Fuse DC + Enhancer (68:32)
    probs = {
        "home_win_prob": float(dc_pred["home_win_prob"]),
        "draw_prob": float(dc_pred["draw_prob"]),
        "away_win_prob": float(dc_pred["away_win_prob"]),
    }
    probs.update(fuse_outcome_probabilities(probs, {
        "home_win_prob": float(enh_pred["home_win_prob"]),
        "draw_prob": float(enh_pred["draw_prob"]),
        "away_win_prob": float(enh_pred["away_win_prob"]),
    }, base_weight=0.68))

    # Layer 3: Elo
    elo = EloRatingSystem()
    elo.fit(df)
    elo_pred = elo.predict(home_team, away_team, is_neutral=is_neutral, competition_weight=competition_weight)
    probs.update(fuse_elo_probabilities(probs, elo_pred, elo_weight=0.15))

    return {
        "home_team": home_team,
        "away_team": away_team,
        "competition": competition,
        "is_neutral": is_neutral,
        "home_win_prob": probs["home_win_prob"],
        "draw_prob": probs["draw_prob"],
        "away_win_prob": probs["away_win_prob"],
        "home_xg": float(dc_pred["home_xg"]),
        "away_xg": float(dc_pred["away_xg"]),
        "top3_scores": dc_pred.get("top3_scores", []),
        "elo": {
            "home_elo": elo_pred.home_elo,
            "away_elo": elo_pred.away_elo,
            "rating_gap": elo_pred.rating_gap,
            "k_factor": elo_pred.k_factor,
        },
        "pipeline": {
            "dc_converged": dc_fit.converged,
            "dc_nll": dc_fit.final_neg_log_likelihood,
            "enhancer_rows": getattr(enhancer, "_training_rows", len(df)),
            "elo_matches": getattr(elo, "_match_count", len(df)),
            "training_rows": len(df),
        },
    }


async def main(home: str, away: str, competition: str, neutral: bool = False) -> None:
    result = await fast_predict(home, away, competition=competition, is_neutral=neutral)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fast numeric prediction")
    parser.add_argument("--home", required=True)
    parser.add_argument("--away", required=True)
    parser.add_argument("--competition", default="Premier League")
    parser.add_argument("--neutral", action="store_true")
    parser.add_argument("--json", action="store_true", help="JSON output only")
    args = parser.parse_args()
    asyncio.run(main(args.home, args.away, args.competition, args.neutral))

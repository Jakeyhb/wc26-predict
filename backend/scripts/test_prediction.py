from __future__ import annotations

import asyncio
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import AsyncSessionLocal
from app.logging import configure_logging
from app.services.calibration import IsotonicCalibrator
from app.services.dixon_coles import DixonColesModel, load_training_frame, WC26_FIFA_TIERS, split_train_holdout_frame
from app.services.elo_ratings import EloRatingSystem, fuse_elo_probabilities
from app.services.tabular_match_model import TabularMatchEnhancer
from app.services.tabular_match_model import fuse_outcome_probabilities


async def run() -> None:
    async with AsyncSessionLocal() as db:
        matches_df = await load_training_frame(db, competition_type="national", team_type="national")

    if matches_df.empty:
        raise RuntimeError("No historical matches found in database.")
    if len(matches_df) < 10:
        raise RuntimeError(f"Not enough historical matches to validate prediction pipeline: {len(matches_df)}")

    train_df, holdout_df = split_train_holdout_frame(matches_df, holdout_ratio=0.1)
    team_info = {}
    for team_name in set(train_df["home_team"]).union(train_df["away_team"]):
        team_info[team_name] = {"confederation": "FIFA", "fifa_tier": WC26_FIFA_TIERS.get(team_name, 0)}
    model = DixonColesModel()
    model.set_team_info(team_info)
    fit_summary = model.fit(train_df)
    enhancer = TabularMatchEnhancer()
    enhancer_summary = enhancer.fit(train_df)

    print("Training Summary")
    print(f"  converged: {fit_summary.converged}")
    print(f"  parameter_count: {fit_summary.parameter_count}")
    print(f"  final_neg_log_likelihood: {fit_summary.final_neg_log_likelihood:.6f}")
    print(f"  message: {fit_summary.message}")
    print(f"  enhancer_rows: {enhancer_summary.training_rows}")
    print(f"  enhancer_features: {enhancer_summary.feature_count}")

    base_prediction = model.predict_match("Brazil", "France", is_neutral_venue=True)
    enhancer_prediction = enhancer.predict_match(
        home_team="Brazil",
        away_team="France",
        match_date=train_df["match_date"].max().to_pydatetime(),
        competition_weight=1.0,
        is_neutral_venue=True,
        training_df=train_df,
        rest_days={"home": 5, "away": 5},
    )
    prediction = {
        **base_prediction,
        **fuse_outcome_probabilities(
            {
                "home_win_prob": float(base_prediction["home_win_prob"]),
                "draw_prob": float(base_prediction["draw_prob"]),
                "away_win_prob": float(base_prediction["away_win_prob"]),
            },
            {
                "home_win_prob": float(enhancer_prediction["home_win_prob"]),
                "draw_prob": float(enhancer_prediction["draw_prob"]),
                "away_win_prob": float(enhancer_prediction["away_win_prob"]),
            },
            base_weight=0.68,
        ),
    }

    # Elo blending
    elo = EloRatingSystem()
    elo.fit(train_df)
    elo_pred = elo.predict("Brazil", "France", is_neutral=True, competition_weight=1.0)
    prediction = {
        **prediction,
        **fuse_elo_probabilities(prediction, elo_pred, elo_weight=0.15),
    }
    print(f"\n  elo_home: {elo_pred.home_elo:.1f}  elo_away: {elo_pred.away_elo:.1f}  rating_gap: {elo_pred.rating_gap:.1f}")
    print(f"  elo_raw: H={elo_pred.home_win_prob:.4f} D={elo_pred.draw_prob:.4f} A={elo_pred.away_win_prob:.4f}")

    print("\\nBrazil vs France (Dixon+Enhancer+Elo)")
    print(f"  home_win_prob: {prediction['home_win_prob']:.4f}")
    print(f"  draw_prob: {prediction['draw_prob']:.4f}")
    print(f"  away_win_prob: {prediction['away_win_prob']:.4f}")
    print(f"  home_xg: {prediction['home_xg']:.4f}")
    print(f"  away_xg: {prediction['away_xg']:.4f}")
    print(f"  top3_scores: {prediction['top3_scores']}")
    print(f"  enhancer_recent_xg_gap: {enhancer_prediction['feature_snapshot']['recent_xg_gap']:.4f}")

    evaluation = model.evaluate(holdout_df)
    print("\nHoldout Evaluation")
    print(f"  rows: {len(holdout_df)}")
    print(f"  brier_score: {evaluation['brier_score']:.6f}")
    print(f"  log_loss: {evaluation['log_loss']:.6f}")
    print(f"  top3_hit_rate: {evaluation['top3_hit_rate']:.4f}")
    calibrator = IsotonicCalibrator()
    try:
        calibrator.load("backend/model_artifacts/calibrator.json")
    except Exception:
        pass
    print(f"  calibration_enabled: {calibrator.is_fitted}")


def main() -> None:
    configure_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()

"""Bivariate Weibull Count Model via penaltyblog.

The Weibull model assumes goal inter-arrival times follow a Weibull
distribution (not exponential/Poisson), capturing momentum effects.
A Frank Copula introduces inter-team correlation, making it better
than independent Poisson for over/under 2.5 goal predictions.

Reference: Boshnakov, Kharrat & McHale (2017).

Integration: Optional complement to Dixon-Coles, weighted ~15% in UCL scenes.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class WeibullWrapper:
    """Wrapper around penaltyblog WeibullCopulaGoalsModel."""

    def __init__(self):
        self._model: Any | None = None
        self._fitted: bool = False

    def fit(self, df: pd.DataFrame) -> bool:
        """Fit the Weibull model on training data.

        Returns True if fitting succeeded, False otherwise.
        NOTE: WeibullCopulaGoalsModel.fit() has no timeout mechanism; on large
        datasets this may block for minutes.  Callers should budget accordingly.
        """
        try:
            from penaltyblog.models import WeibullCopulaGoalsModel

            wc = WeibullCopulaGoalsModel(
                goals_home=df["home_goals"].values,
                goals_away=df["away_goals"].values,
                teams_home=df["home_team"].values,
                teams_away=df["away_team"].values,
                weights=df.get("competition_weight", None),
            )
            wc.fit()
            self._model = wc
            self._fitted = True
            logger.info("Weibull model fitted successfully")
            return True
        except Exception as e:
            logger.warning("Weibull model fit failed: %s", e)
            self._fitted = False
            return False

    def predict(self, home_team: str, away_team: str, neutral: bool = True) -> dict[str, float] | None:
        """Predict win/draw/loss probabilities using fitted Weibull model."""
        if not self._fitted or self._model is None:
            return None
        try:
            grid = self._model.predict(home_team, away_team, neutral=neutral)
            return {
                "home_win_prob": float(grid.home_win),
                "draw_prob": float(grid.draw),
                "away_win_prob": float(grid.away_win),
            }
        except Exception as e:
            logger.warning("Weibull predict failed: %s", e)
            return None


def fuse_weibull_probs(base_probs: dict, wb_pred: dict | None, wb_weight: float = 0.15) -> dict:
    """Blend Weibull probabilities into the ensemble.

    If Weibull failed to fit/predict, returns base_probs unchanged.
    """
    if wb_pred is None:
        return dict(base_probs)

    fused = {}
    for key in ("home_win_prob", "draw_prob", "away_win_prob"):
        fused[key] = base_probs[key] * (1.0 - wb_weight) + wb_pred[key] * wb_weight
    total = fused["home_win_prob"] + fused["draw_prob"] + fused["away_win_prob"]
    for key in fused:
        fused[key] /= total

    return fused

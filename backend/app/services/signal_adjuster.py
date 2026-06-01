from __future__ import annotations

import math
from typing import Any

import numpy as np

from app.logging import get_logger

logger = get_logger(__name__)


class SignalAdjuster:
    MAX_ADJUSTMENT = {
        "injury_key_striker": 0.15,
        "injury_key_goalkeeper": 0.10,
        "return_key_player": 0.08,
        "major_rotation": 0.12,
        "travel_fatigue": 0.06,
    }

    # World Cup venue altitudes (meters)
    VENUE_ALTITUDE = {
        "Estadio Azteca": 2240,       # Mexico City
        "Estadio BBVA": 537,           # Monterrey
        "Estadio Akron": 1560,         # Guadalajara
    }
    HIGH_ALTITUDE_THRESHOLD = 1500   # Significant physiological impact
    HIGH_ALTITUDE_XG_FACTOR = 0.95   # Reduce xG for both teams at altitude

    def apply_venue_factors(
        self,
        home_xg: float,
        away_xg: float,
        venue: str | None = None,
        match_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Apply venue-based adjustments (altitude, etc.) to xG values.

        Called BEFORE signal adjustment so venue effects compose with
        manual-event signal effects.

        Returns {home_xg, away_xg, risk_tags, adjustment_log}
        """
        risk_tags: list[str] = []
        adjustment_log: list[dict[str, Any]] = []
        adjusted_home_xg = float(home_xg)
        adjusted_away_xg = float(away_xg)

        # Try to get venue from match_context if not explicitly provided
        venue_name = venue
        if not venue_name and match_context:
            venue_name = match_context.get("venue", match_context.get("venue_name"))
        if not venue_name and match_context:
            # Try to find venue in competition-specific keys
            venue_name = match_context.get("stadium")

        if venue_name and venue_name in self.VENUE_ALTITUDE:
            altitude = self.VENUE_ALTITUDE[venue_name]
            if altitude >= self.HIGH_ALTITUDE_THRESHOLD:
                factor = self.HIGH_ALTITUDE_XG_FACTOR
                adjusted_home_xg *= factor
                adjusted_away_xg *= factor
                risk_tags.append("高海拔场地")
                adjustment_log.append({
                    "type": "venue_altitude",
                    "venue": venue_name,
                    "altitude_m": altitude,
                    "xg_factor": factor,
                    "description": f"{venue_name} 海拔 {altitude}m，双方 xG × {factor}",
                })

        return {
            "home_xg": adjusted_home_xg,
            "away_xg": adjusted_away_xg,
            "risk_tags": risk_tags,
            "adjustment_log": adjustment_log,
        }

    async def apply_signals(
        self,
        base_prediction: dict[str, Any],
        approved_signals: list[dict[str, Any]],
        match_context: dict[str, Any],
    ) -> dict[str, Any]:
        adjusted_home_xg = float(base_prediction["home_xg"])
        adjusted_away_xg = float(base_prediction["away_xg"])
        adjustment_log: list[dict[str, Any]] = []

        for signal in approved_signals:
            team_side = self._resolve_team_side(signal, match_context)
            if team_side is None:
                continue
            scale = self._signal_adjustment_scale(signal)
            confidence = float(signal.get("confidence", 0.5))

            # Dynamic weight multiplier from signal_track_record
            multiplier = 1.0
            signal_type = signal["signal_type"]
            try:
                multiplier = await self._get_dynamic_multiplier(signal_type)
            except Exception:
                pass

            magnitude = scale * confidence * multiplier
            if magnitude == 0:
                continue
            if signal_type == "injury":
                if team_side == "home":
                    adjusted_home_xg *= 1 - magnitude
                else:
                    adjusted_away_xg *= 1 - magnitude
            elif signal_type == "return":
                if team_side == "home":
                    adjusted_home_xg *= 1 + magnitude
                else:
                    adjusted_away_xg *= 1 + magnitude
            elif signal_type in {"travel", "weather"}:
                if team_side == "home":
                    adjusted_home_xg *= 1 - magnitude
                    adjusted_away_xg *= 1 + (magnitude / 2)
                else:
                    adjusted_away_xg *= 1 - magnitude
                    adjusted_home_xg *= 1 + (magnitude / 2)
            elif signal_type == "lineup_hint":
                if team_side == "home":
                    adjusted_home_xg *= 1 - (magnitude / 2)
                else:
                    adjusted_away_xg *= 1 - (magnitude / 2)

            adjustment_log.append(
                {
                    "signal_id": str(signal.get("id")),
                    "team_side": team_side,
                    "signal_type": signal["signal_type"],
                    "magnitude": round(magnitude, 4),
                }
            )

        score_matrix = self._rebuild_matrix(adjusted_home_xg, adjusted_away_xg)
        top3_scores = self._top_scores(score_matrix)
        home_win_prob = float(np.tril(score_matrix, -1).sum())
        draw_prob = float(np.trace(score_matrix))
        away_win_prob = float(np.triu(score_matrix, 1).sum())

        confidence_base = float(base_prediction.get("confidence_score", 0.6))
        confidence_penalty = min(0.2, 0.03 * len(adjustment_log))
        confidence_bonus = min(
            0.08,
            sum(float(signal.get("confidence", 0.0)) * 0.01 for signal in approved_signals if signal["signal_type"] == "return"),
        )
        confidence_score = max(0.05, min(0.99, confidence_base - confidence_penalty + confidence_bonus))

        return {
            **base_prediction,
            "home_win_prob": home_win_prob,
            "draw_prob": draw_prob,
            "away_win_prob": away_win_prob,
            "home_xg": adjusted_home_xg,
            "away_xg": adjusted_away_xg,
            "score_matrix": score_matrix.tolist(),
            "top3_scores": top3_scores,
            "adjustment_log": adjustment_log,
            "confidence_score": confidence_score,
            "confidence_adjustment": {
                "base": confidence_base,
                "penalty": confidence_penalty,
                "bonus": confidence_bonus,
            },
            "risk_tags": self._calculate_risk_tags(approved_signals, match_context),
        }

    def _resolve_team_side(self, signal: dict[str, Any], context: dict[str, Any]) -> str | None:
        team_id = signal.get("team_id")
        if team_id and str(team_id) == str(context.get("home_team_id")):
            return "home"
        if team_id and str(team_id) == str(context.get("away_team_id")):
            return "away"

        summary = signal.get("summary_zh", "")
        home_name = str(context.get("home_team_name", ""))
        away_name = str(context.get("away_team_name", ""))
        if home_name and home_name in summary:
            return "home"
        if away_name and away_name in summary:
            return "away"
        return None

    def _signal_adjustment_scale(self, signal: dict[str, Any]) -> float:
        signal_type = signal["signal_type"]
        key_players = [player.lower() for player in signal.get("key_players", [])]
        summary = str(signal.get("summary_zh", "")).lower()
        expected_minutes_delta = signal.get("expected_minutes_delta")
        availability = str(signal.get("normalized_availability", "") or "").lower()
        if expected_minutes_delta is not None:
            try:
                delta_scale = min(0.16, abs(float(expected_minutes_delta)) / 90 * 0.15)
                if delta_scale > 0:
                    return delta_scale
            except (TypeError, ValueError):
                pass
        if signal_type == "injury":
            if availability in {"out", "suspended"}:
                return self.MAX_ADJUSTMENT["injury_key_striker"] if key_players else 0.10
            if availability == "doubtful":
                return 0.06
            if any(token in summary for token in ("门将", "goalkeeper", "keeper")):
                return self.MAX_ADJUSTMENT["injury_key_goalkeeper"]
            if key_players:
                return self.MAX_ADJUSTMENT["injury_key_striker"]
            return 0.08
        if signal_type == "return":
            if availability in {"available", "likely_start"}:
                return self.MAX_ADJUSTMENT["return_key_player"] if key_players else 0.06
            return self.MAX_ADJUSTMENT["return_key_player"] if key_players else 0.05
        if signal_type == "travel":
            return self.MAX_ADJUSTMENT["travel_fatigue"]
        if signal_type == "lineup_hint":
            return self.MAX_ADJUSTMENT["major_rotation"]
        if signal_type == "weather":
            return 0.04
        return 0.03

    async def _get_dynamic_multiplier(self, signal_type: str) -> float:
        """Read accuracy_rate from signal_track_record to scale magnitude.

        Historical accuracy → multiplier:
          rate > 0.80 → 1.0  (proven reliable)
          rate 0.50-0.80 → 0.8 (moderate evidence)
          rate < 0.50 → 0.5  (poor track record)
          no history → 0.7    (conservative default — no empirical basis)

        Returns multiplier in [0.4, 1.0].
        """
        try:
            from app.database import AsyncSessionLocal
            from sqlalchemy import text
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    text("SELECT accuracy_rate, total_used FROM signal_track_record WHERE signal_type = :st"),
                    {"st": signal_type.upper()},
                )
                row = result.fetchone()
                if row and row[1] >= 3:  # Require at least 3 uses to trust history
                    rate = float(row[0])
                    if rate > 0.80:
                        return 1.0
                    elif rate > 0.50:
                        return 0.8
                    else:
                        return 0.5
        except Exception:
            pass
        return 0.7  # Conservative default: no empirical basis for magnitude

    def _rebuild_matrix(self, home_xg: float, away_xg: float, max_goals: int = 5) -> np.ndarray:
        matrix = np.zeros((max_goals + 1, max_goals + 1))
        for home_goals in range(max_goals + 1):
            for away_goals in range(max_goals + 1):
                matrix[home_goals, away_goals] = self._poisson_pmf(home_goals, home_xg) * self._poisson_pmf(
                    away_goals, away_xg
                )
        total = matrix.sum()
        return matrix / total if total > 0 else matrix

    @staticmethod
    def _poisson_pmf(goals: int, rate: float) -> float:
        rate = max(rate, 1e-8)
        return math.exp(goals * math.log(rate) - rate - math.lgamma(goals + 1))

    def _top_scores(self, matrix: np.ndarray) -> list[dict[str, float | str]]:
        scores: list[tuple[str, float]] = []
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                scores.append((f"{i}:{j}", float(matrix[i, j])))
        return [{"score": score, "prob": prob} for score, prob in sorted(scores, key=lambda item: item[1], reverse=True)[:3]]

    def _calculate_risk_tags(self, signals: list[dict[str, Any]], context: dict[str, Any]) -> list[str]:
        tags: set[str] = set()
        for signal in signals:
            signal_type = signal["signal_type"]
            confidence = float(signal.get("confidence", 0.0))
            if signal_type == "lineup_hint" and confidence < 0.6:
                tags.add("首发不确定")
            if signal_type == "travel":
                tags.add("旅行疲劳")
            if signal_type == "injury" and signal.get("key_players"):
                tags.add("关键球员缺阵")
            if signal_type == "weather":
                tags.add("天气扰动")
            if signal.get("normalized_availability") == "out":
                tags.add("关键球员缺阵")
            if signal.get("contradiction_risk") == "high":
                tags.add("情报冲突")
        if context.get("stage") == "group" and context.get("matchday") == 3:
            tags.add("小组赛轮换风险")
        if float(context.get("travel_km", 0) or 0) > 3000:
            tags.add("旅行距离较长")
        weather = context.get("weather", {}) or {}
        precipitation = float(weather.get("precipitation_mm", 0) or 0)
        wind_speed = float(weather.get("wind_speed_kmh", 0) or 0)
        temperature = weather.get("temperature_c")
        if precipitation > 5:
            tags.add("大雨天气")
        elif precipitation > 1:
            tags.add("雨天影响")
        if wind_speed > 40:
            tags.add("强风天气")
        if temperature is not None and float(temperature) > 32:
            tags.add("高温酷暑")
        if temperature is not None and float(temperature) < 5:
            tags.add("低温条件")
        return sorted(tags)

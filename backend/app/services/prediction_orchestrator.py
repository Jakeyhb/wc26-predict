from __future__ import annotations

import asyncio
import math
from dataclasses import asdict
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from uuid import UUID

import numpy as np
import pandas as pd
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.exceptions import NotFoundError
from app.logging import get_logger
from app.models import Match, MatchResult, NewsSignal, PredictionRun
from app.models.enums import CompetitionType, PredictionRunType, ReviewStatus
from app.services.calibration import IsotonicCalibrator
from app.services.dixon_coles import DixonColesModel, load_training_frame
from app.services.model_cache_disk import load_dc_from_disk, save_dc_model_to_disk
from app.services.elo_ratings import EloRatingSystem, fuse_elo_probabilities
from app.services.football_data_service import ELITE_CLUB_POOL_CODES
from app.services.football_data_service import EUROPEAN_ELITE_POOL_CODES
from app.services.football_data_service import FootballDataService
from app.services.injury_data import InjuryDataService, fuse_injury_signals
from app.services.market_calibrator import get_calibrator
from app.services.signal_adjuster import SignalAdjuster
from app.services.tabular_match_model import TabularMatchEnhancer
from app.services.tabular_match_model import fuse_outcome_probabilities
from app.services.weights import get_weight_config
from app.services.weather_service import WeatherService
from app.utils.datetime import utc_now

settings = get_settings()
logger = get_logger(__name__)


class PredictionOrchestrator:
    def __init__(self) -> None:
        self.signal_adjuster = SignalAdjuster()
        self.weather_service = WeatherService()
        self.elo = EloRatingSystem()
        self._elo_fitted = False
        self.market_calibrator = get_calibrator()
        self.injury_service = InjuryDataService()

    async def run_prediction(
        self,
        match_id: UUID,
        run_type: str,
        db: AsyncSession,
    ) -> UUID:
        result = await db.execute(
            select(Match)
            .options(
                selectinload(Match.home_team),
                selectinload(Match.away_team),
                selectinload(Match.news_signals),
            )
            .where(Match.id == match_id)
        )
        match = result.scalar_one_or_none()
        if match is None:
            raise NotFoundError("Match not found")

        prediction_run_type = PredictionRunType(run_type)
        as_of_time = self._resolve_as_of_time(match, prediction_run_type)
        training_df, training_scope = await self._load_training_frame_for_match(match, as_of_time, db)
        if len(training_df) < 8:
            raise ValueError("Not enough finished matches to train prediction model")
        match_context = await self._build_match_context(match, as_of_time, db)

        fit_summary, base_prediction, model_meta = await self._build_base_prediction(
            match,
            training_df,
            match_context,
            training_scope=training_scope,
        )
        calibrator = self._load_calibrator()
        calibrator_stats = calibrator.calibration_stats()
        calibration_applied = False
        if calibrator.is_fitted:
            calibrated_probs = calibrator.calibrate(
                {
                    "home_win_prob": float(base_prediction["home_win_prob"]),
                    "draw_prob": float(base_prediction["draw_prob"]),
                    "away_win_prob": float(base_prediction["away_win_prob"]),
                }
            )
            base_prediction = {**base_prediction, **calibrated_probs}
            calibration_applied = True

        approved_result = await db.execute(
            select(NewsSignal)
            .where(
                NewsSignal.match_id == match.id,
                NewsSignal.review_status == ReviewStatus.APPROVED,
                NewsSignal.enters_model.is_(True),
                NewsSignal.evidence_id.isnot(None),
                NewsSignal.created_at <= as_of_time,
            )
            .order_by(NewsSignal.created_at.asc())
        )
        approved_signals = approved_result.scalars().all()
        approved_signal_payload = [
            {
                "id": str(signal.id),
                "team_id": str(signal.team_id) if signal.team_id else None,
                "signal_type": str(signal.signal_type),
                "impact_direction": str(signal.impact_direction),
                "confidence": signal.confidence,
                "summary_zh": signal.summary_zh,
                "key_players": signal.key_players,
                "player_name": signal.player_name,
                "claim": signal.claim,
                "evidence_snippet": signal.evidence_snippet,
                "normalized_availability": signal.normalized_availability,
                "expected_minutes_delta": signal.expected_minutes_delta,
                "effective_until": signal.effective_until.isoformat() if signal.effective_until else None,
                "contradiction_risk": signal.contradiction_risk,
                "conflict_group_id": signal.conflict_group_id,
                "source_reliability": signal.source_reliability,
                "reviewed_at": signal.reviewed_at.isoformat() if signal.reviewed_at else None,
            }
            for signal in approved_signals
        ]

        if model_meta["mode"] == "trained":
            confidence_score = min(
                0.95,
                0.45 + min(0.25, len(training_df) / 300) + abs(base_prediction["home_win_prob"] - base_prediction["away_win_prob"]) * 0.2,
            )
            # Data completeness penalty: knowledge gaps reduce confidence
            data_penalties: list[tuple[str, float]] = []
            # 1. No injury/signal intelligence
            if len(approved_signal_payload) == 0:
                data_penalties.append(("no_intel_signals", 0.05))
            # 2. Sparse training data for club-level granularity
            if len(training_df) < 200:
                data_penalties.append(("sparse_training", 0.10))
            elif len(training_df) < 500:
                data_penalties.append(("sparse_training", 0.05))
            # 3. Market divergence >8pp = market knows something we don't
            market_result = model_meta.get("market_result", {})
            if market_result.get("divergence_triggered"):
                data_penalties.append(("market_divergence", 0.05))
            # 4. Odds data was stale or unavailable
            if not market_result.get("market_applied"):
                data_penalties.append(("no_market_calibration", 0.03))

            total_penalty = sum(p for _, p in data_penalties)
            confidence_score = max(0.30, confidence_score - total_penalty)
            # Add penalty descriptors as risk tags for transparency
            if data_penalties:
                penalty_tags = [f"数据缺失-{reason}" for reason, _ in data_penalties]
                base_prediction.setdefault("risk_tags", [])
                base_prediction["risk_tags"] = list(set(base_prediction.get("risk_tags", []) + penalty_tags))
            adjusted_prediction = await self.signal_adjuster.apply_signals(
                {**base_prediction, "confidence_score": confidence_score},
                approved_signal_payload,
                match_context,
            )
            if calibrator.is_fitted:
                adjusted_prediction = {
                    **adjusted_prediction,
                    **calibrator.calibrate(
                        {
                            "home_win_prob": float(adjusted_prediction["home_win_prob"]),
                            "draw_prob": float(adjusted_prediction["draw_prob"]),
                            "away_win_prob": float(adjusted_prediction["away_win_prob"]),
                        }
                    ),
                }
            risk_tags = adjusted_prediction["risk_tags"]
            adjustment_log = adjusted_prediction.get("adjustment_log", [])
            stored_signals = approved_signal_payload
        else:
            weather_tags = match_context.get("weather", {}).get("weather_impact_tags", [])
            adjusted_prediction = {
                **base_prediction,
                "confidence_score": min(0.6, base_prediction.get("confidence_score", 0.42)),
                "risk_tags": sorted({"模型训练超时，使用基础预测", *weather_tags}),
                "adjustment_log": [],
            }
            risk_tags = adjusted_prediction["risk_tags"]
            adjustment_log = []
            stored_signals = []

        prediction_run = PredictionRun(
            match_id=match.id,
            run_type=prediction_run_type,
            model_version=model_meta["model_version"],
            as_of_time=as_of_time,
            home_win_prob=adjusted_prediction["home_win_prob"],
            draw_prob=adjusted_prediction["draw_prob"],
            away_win_prob=adjusted_prediction["away_win_prob"],
            home_xg=adjusted_prediction["home_xg"],
            away_xg=adjusted_prediction["away_xg"],
            score_matrix=adjusted_prediction["score_matrix"],
            top3_scores=adjusted_prediction["top3_scores"],
            confidence_score=adjusted_prediction["confidence_score"],
            risk_tags=risk_tags,
            input_feature_snapshot={
                "training_rows": len(training_df),
                "fit_summary": asdict(fit_summary),
                "match_context": match_context,
                "adjustment_log": adjustment_log,
                "prediction_mode": model_meta["mode"],
                "timeout_fallback": model_meta["mode"] == "fallback",
                "calibration_applied": calibration_applied,
                "calibration_stats": calibrator_stats,
                "model_artifact_path": model_meta.get("artifact_path"),
                "training_scope": training_scope,
                "ensemble": model_meta.get("ensemble"),
                "enhancer": model_meta.get("enhancer"),
            },
            approved_signals=stored_signals,
        )
        prediction_run.match = match
        db.add(prediction_run)
        await db.flush()
        await db.commit()

        try:
            from app.workers.tasks import generate_article_task

            generate_article_task.delay(str(prediction_run.id))
        except Exception as exc:
            logger.warning("Failed to enqueue article generation for %s: %s", prediction_run.id, exc)
        return prediction_run.id

    def _resolve_as_of_time(self, match: Match, run_type: PredictionRunType):
        now = utc_now()
        kickoff = self._ensure_utc(match.match_date)
        if run_type == PredictionRunType.T_MINUS_24H:
            target = kickoff - timedelta(hours=24)
        elif run_type == PredictionRunType.T_MINUS_3H:
            target = kickoff - timedelta(hours=3)
        else:
            target = kickoff - timedelta(minutes=1)
        return min(now, target)

    async def _build_base_prediction(
        self,
        match: Match,
        training_df: pd.DataFrame,
        match_context: dict[str, object],
        *,
        training_scope: dict[str, object],
    ):
        model = DixonColesModel()
        try:
            # Check disk cache first — avoids expensive re-fit when data unchanged
            competition_type = str(match.competition_type or "national")
            cached = load_dc_from_disk(competition_type, training_df)
            if cached:
                from app.services.model_cache import CachedDC
                model.attack_params = cached.attack_params
                model.defense_params = cached.defense_params
                model.home_advantage = cached.home_advantage
                model.rho = cached.rho
                model._team_order = cached._team_order
                model.trained_at = cached.trained_at
                fit_summary = type("FitSummary", (), {
                    "final_neg_log_likelihood": 0.0,
                    "converged": True,
                    "message": "loaded from disk cache",
                })()
            else:
                fit_summary = await asyncio.wait_for(asyncio.to_thread(model.fit, training_df), timeout=30)
                save_dc_model_to_disk(model, competition_type, training_df)
            base_prediction = model.predict_match(
                match.home_team.name,
                match.away_team.name,
                is_neutral_venue=match.is_neutral_venue,
            )
            competition_code = self._competition_code_for_match(match)
            competition_type = str(match.competition_type)
            artifact_path = settings.model_artifact_dir / (
                f"{competition_type}_{competition_code}_{match.id}-{utc_now().strftime('%Y%m%d%H%M%S')}.json"
            )
            model.save(str(artifact_path))
            # ── Weight config (unified source) ──
            competition_name = getattr(match, "competition", "")
            wc = get_weight_config(competition_name, getattr(match, "stage", ""))

            enhancer_meta = await self._build_enhancer_prediction(match, training_df, match_context)
            if enhancer_meta["enabled"]:
                base_prediction = {
                    **base_prediction,
                    **fuse_outcome_probabilities(
                        {
                            "home_win_prob": float(base_prediction["home_win_prob"]),
                            "draw_prob": float(base_prediction["draw_prob"]),
                            "away_win_prob": float(base_prediction["away_win_prob"]),
                        },
                        enhancer_meta["probabilities"],
                        base_weight=wc.dc,
                    ),
                }

            # Elo blending: fit once, blend every prediction
            if not self._elo_fitted:
                try:
                    self.elo.fit(training_df)
                    self._elo_fitted = True
                except Exception:
                    logger.warning("Elo fitting failed — predictions will skip Elo", exc_info=True)
            if self._elo_fitted:
                try:
                    elo_pred = self.elo.predict(
                        match.home_team.name,
                        match.away_team.name,
                        is_neutral=match.is_neutral_venue,
                        competition_weight=match.competition_weight,
                    )
                    base_prediction = {
                        **base_prediction,
                        **fuse_elo_probabilities(base_prediction, elo_pred, elo_weight=wc.elo),
                    }
                except Exception:
                    logger.warning("Elo prediction failed for %s vs %s — skipping Elo blend",
                                   match.home_team.name, match.away_team.name, exc_info=True)

            # Market calibrator (gracefully skipped if no API key)
            market_result: dict[str, object] = {}
            try:
                market_probs = await self.market_calibrator.fetch_market_probs(
                    match.home_team.name,
                    match.away_team.name,
                    competition_weight=match.competition_weight,
                )
                if market_probs:
                    calibrated = self.market_calibrator.calibrate(
                        base_prediction, market_probs,
                        sample_size=len(training_df),
                    )
                    market_result = dict(calibrated)
                    if calibrated.get("market_applied"):
                        base_prediction = {
                            "home_win_prob": calibrated["home_win_prob"],
                            "draw_prob": calibrated["draw_prob"],
                            "away_win_prob": calibrated["away_win_prob"],
                        }
            except Exception:
                logger.warning("Market calibration failed for %s vs %s — continuing without",
                               match.home_team.name, match.away_team.name, exc_info=True)

            # Injury signal blending
            injury_signals = self.injury_service.generate_signals_for_match(
                match.home_team.name,
                match.away_team.name,
                match_id=match.id,
                home_team_id=match.home_team_id,
                away_team_id=match.away_team_id,
                match_date=match.match_date,
            )
            if injury_signals:
                base_prediction = {
                    **base_prediction,
                    **fuse_injury_signals(
                        base_prediction,
                        injury_signals,
                        home_team=match.home_team.name,
                        away_team=match.away_team.name,
                    ),
                }
            return (
                fit_summary,
                base_prediction,
                {
                    "mode": "trained",
                    "model_version": enhancer_meta["model_version"],
                    "artifact_path": str(artifact_path),
                    "training_scope": training_scope,
                    "ensemble": {
                        "dixon_weight": wc.dc if enhancer_meta["enabled"] else 1.0,
                        "enhancer_weight": wc.enhancer if enhancer_meta["enabled"] else 0.0,
                        "enhancer_enabled": enhancer_meta["enabled"],
                    },
                    "enhancer": enhancer_meta["snapshot"],
                    "market_result": market_result,
                },
            )
        except asyncio.TimeoutError:
            logger.warning("Dixon-Coles training timed out for match %s, falling back to baseline Poisson", match.id)
        except Exception as exc:
            logger.warning("Dixon-Coles training failed for match %s, falling back to baseline Poisson: %s", match.id, exc)

        fit_summary = self._fallback_fit_summary()
        base_prediction = self._build_baseline_prediction(match, training_df)
        return (
            fit_summary,
            base_prediction,
            {
                "mode": "fallback",
                "model_version": f"{settings.prediction_model_version}_fallback",
                "artifact_path": None,
                "training_scope": training_scope,
                "ensemble": {
                    "dixon_weight": 0.0,
                    "enhancer_weight": 0.0,
                    "enhancer_enabled": False,
                },
                "enhancer": {
                    "enabled": False,
                    "reason": "Dixon-Coles fallback path disables enhancer",
                },
            },
        )

    async def _build_enhancer_prediction(
        self,
        match: Match,
        training_df: pd.DataFrame,
        match_context: dict[str, object],
    ) -> dict[str, object]:
        enhancer = TabularMatchEnhancer()
        try:
            fit_summary = await asyncio.wait_for(asyncio.to_thread(enhancer.fit, training_df), timeout=60)
            prediction = enhancer.predict_match(
                home_team=match.home_team.name,
                away_team=match.away_team.name,
                match_date=match.match_date,
                competition_weight=match.competition_weight,
                is_neutral_venue=match.is_neutral_venue,
                training_df=training_df,
                rest_days=match_context.get("rest_days") if isinstance(match_context.get("rest_days"), dict) else None,
            )
            return {
                "enabled": True,
                "probabilities": {
                    "home_win_prob": float(prediction["home_win_prob"]),
                    "draw_prob": float(prediction["draw_prob"]),
                    "away_win_prob": float(prediction["away_win_prob"]),
                },
                "model_version": f"{settings.prediction_model_version}+hgb_v1",
                "snapshot": {
                    "enabled": True,
                    "fit_summary": asdict(fit_summary),
                    "feature_snapshot": prediction["feature_snapshot"],
                    "algorithm": "HistGradientBoostingClassifier",
                },
            }
        except asyncio.TimeoutError:
            logger.warning("Tabular enhancer timed out for match %s, continuing with Dixon-Coles only", match.id)
        except Exception as exc:
            logger.warning("Tabular enhancer failed for match %s, continuing with Dixon-Coles only: %s", match.id, exc)
        return {
            "enabled": False,
            "probabilities": None,
            "model_version": settings.prediction_model_version,
            "snapshot": {
                "enabled": False,
                "algorithm": "HistGradientBoostingClassifier",
            },
        }

    async def _build_match_context(self, match: Match, as_of_time, db: AsyncSession) -> dict[str, object]:
        home_rest = await self._days_since_last_match(match.home_team_id, match.match_date, db)
        away_rest = await self._days_since_last_match(match.away_team_id, match.match_date, db)
        matchday = await self._infer_matchday(match, db)
        weather = await self.weather_service.fetch_match_weather(match.venue, match.match_date)
        weather_tags = self.weather_service.weather_impact_tags(weather)
        weather["weather_impact_tags"] = weather_tags
        return {
            "match_id": str(match.id),
            "stage": (match.stage or "").lower(),
            "matchday": matchday,
            "competition": match.competition,
            "competition_type": str(match.competition_type),
            "competition_code": self._competition_code_for_match(match),
            "home_team_id": str(match.home_team_id),
            "away_team_id": str(match.away_team_id),
            "home_team_name": match.home_team.name,
            "away_team_name": match.away_team.name,
            "rest_days": {
                "home": home_rest,
                "away": away_rest,
            },
            "must_not_lose": False,
            "travel_km": 0,
            "as_of_time": as_of_time.isoformat(),
            "weather": weather,
        }

    async def _days_since_last_match(self, team_id: UUID, match_date, db: AsyncSession) -> int | None:
        result = await db.execute(
            select(Match)
            .where(
                or_(Match.home_team_id == team_id, Match.away_team_id == team_id),
                Match.match_date < match_date,
            )
            .order_by(Match.match_date.desc())
            .limit(1)
        )
        previous = result.scalars().first()
        if previous is None:
            return None
        return (match_date - previous.match_date).days

    async def _infer_matchday(self, match: Match, db: AsyncSession) -> int:
        window_start = match.match_date - timedelta(days=4)
        result = await db.execute(
            select(Match)
            .where(
                Match.competition == match.competition,
                Match.stage == match.stage,
                Match.match_date >= window_start,
                Match.match_date <= match.match_date,
            )
            .order_by(Match.match_date.asc())
        )
        return max(1, len(result.scalars().all()))

    def _fallback_fit_summary(self):
        from app.services.dixon_coles import FitSummary

        return FitSummary(
            parameter_count=0,
            final_neg_log_likelihood=0.0,
            converged=False,
            message="Timed out; used baseline Poisson fallback",
        )

    def _build_baseline_prediction(self, match: Match, training_df: pd.DataFrame) -> dict[str, object]:
        overall_scored = float(
            pd.concat([training_df["home_goals"], training_df["away_goals"]], ignore_index=True).mean()
        )
        overall_scored = max(overall_scored, 0.8)

        def team_strength(team_name: str):
            home_rows = training_df[training_df["home_team"] == team_name]
            away_rows = training_df[training_df["away_team"] == team_name]
            scored = pd.concat([home_rows["home_goals"], away_rows["away_goals"]], ignore_index=True)
            conceded = pd.concat([home_rows["away_goals"], away_rows["home_goals"]], ignore_index=True)
            attack = float(scored.mean()) / overall_scored if not scored.empty else 1.0
            defense = float(conceded.mean()) / overall_scored if not conceded.empty else 1.0
            return max(0.5, attack), max(0.5, defense)

        home_attack, home_defense = team_strength(match.home_team.name)
        away_attack, away_defense = team_strength(match.away_team.name)
        home_advantage = 1.08 if not match.is_neutral_venue else 1.0
        home_xg = max(0.2, overall_scored * home_attack * away_defense * home_advantage)
        away_xg = max(0.2, overall_scored * away_attack * home_defense)
        matrix = self._poisson_score_matrix(home_xg, away_xg)

        flattened: list[tuple[str, float]] = []
        for home_goals in range(matrix.shape[0]):
            for away_goals in range(matrix.shape[1]):
                flattened.append((f"{home_goals}:{away_goals}", float(matrix[home_goals, away_goals])))

        return {
            "home_win_prob": float(np.tril(matrix, -1).sum()),
            "draw_prob": float(np.trace(matrix)),
            "away_win_prob": float(np.triu(matrix, 1).sum()),
            "home_xg": float(home_xg),
            "away_xg": float(away_xg),
            "score_matrix": matrix.tolist(),
            "top3_scores": [
                {"score": score, "prob": prob}
                for score, prob in sorted(flattened, key=lambda item: item[1], reverse=True)[:3]
            ],
            "confidence_score": 0.42,
            "risk_tags": [],
            "model_params_used": {
                "home_attack": round(home_attack, 4),
                "home_defense": round(home_defense, 4),
                "away_attack": round(away_attack, 4),
                "away_defense": round(away_defense, 4),
                "fallback": True,
            },
        }

    def _load_calibrator(self) -> IsotonicCalibrator:
        calibrator = IsotonicCalibrator()
        try:
            calibrator.load(str(settings.model_artifact_dir / "calibrator.json"))
        except Exception as exc:
            logger.warning("Failed to load calibrator artifact: %s", exc)
        return calibrator

    async def _load_training_frame_for_match(
        self,
        match: Match,
        as_of_time: datetime,
        db: AsyncSession,
    ) -> tuple[pd.DataFrame, dict[str, object]]:
        competition_type = CompetitionType(str(match.competition_type))
        competition_code = self._competition_code_for_match(match)
        if competition_type == CompetitionType.NATIONAL:
            frame = await load_training_frame(
                db,
                as_of_time=as_of_time,
                competition_type=CompetitionType.NATIONAL.value,
                team_type="national",
            )
            return frame, {
                "mode": "national_only",
                "competition": match.competition,
                "competition_code": competition_code,
                "competition_type": competition_type.value,
                "fallback_pool": None,
            }

        if competition_type == CompetitionType.CLUB:
            primary = await load_training_frame(
                db,
                as_of_time=as_of_time,
                competition=match.competition,
                competition_type=CompetitionType.CLUB.value,
                team_type="club",
            )
            if len(primary) >= 50:
                return primary, {
                    "mode": "same_league",
                    "competition": match.competition,
                    "competition_code": competition_code,
                    "competition_type": competition_type.value,
                    "fallback_pool": None,
                }
            fallback_competitions = [FootballDataService.competition_name_from_code(code) for code in ELITE_CLUB_POOL_CODES]
            fallback = await load_training_frame(
                db,
                as_of_time=as_of_time,
                competitions=fallback_competitions,
                competition_type=CompetitionType.CLUB.value,
                team_type="club",
            )
            return fallback, {
                "mode": "elite_club_pool",
                "competition": match.competition,
                "competition_code": competition_code,
                "competition_type": competition_type.value,
                "fallback_pool": list(ELITE_CLUB_POOL_CODES),
            }

        primary = await load_training_frame(
            db,
            as_of_time=as_of_time,
            competition=match.competition,
            competition_type=CompetitionType.CUP.value,
            team_type="club",
        )
        if len(primary) >= 50:
            return primary, {
                "mode": "same_cup",
                "competition": match.competition,
                "competition_code": competition_code,
                "competition_type": competition_type.value,
                "fallback_pool": None,
            }
        fallback_competitions = [FootballDataService.competition_name_from_code(code) for code in EUROPEAN_ELITE_POOL_CODES]
        fallback = await load_training_frame(
            db,
            as_of_time=as_of_time,
            competitions=fallback_competitions,
            team_type="club",
        )
        return fallback, {
            "mode": "elite_cup_pool",
            "competition": match.competition,
            "competition_code": competition_code,
            "competition_type": competition_type.value,
            "fallback_pool": list(EUROPEAN_ELITE_POOL_CODES),
        }

    @staticmethod
    def _competition_code_for_match(match: Match) -> str:
        return FootballDataService.competition_name_to_code(match.competition) or "UNK"

    def _poisson_score_matrix(self, home_xg: float, away_xg: float, max_goals: int = 5) -> np.ndarray:
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

    @staticmethod
    def _ensure_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

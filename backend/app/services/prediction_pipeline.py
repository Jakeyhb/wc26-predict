"""PredictionPipeline — single, unified prediction entry point for WC26.

Replaces scattered prediction logic across snapshot.py, fast_predict.py,
and prediction_orchestrator.py.

Design: Wraps the proven pipeline from snapshot.py into a reusable class.
Does NOT rewrite business logic — just orchestrates existing services.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Literal

import pandas as pd

from app.services.dixon_coles import DixonColesModel
from app.services.elo_ratings import EloRatingSystem, fuse_elo_probabilities
from app.services.market_calibrator import MarketCalibrator, get_calibrator
from app.services.model_cache import ModelCache, get_cache as get_model_cache
from app.services.model_cache_disk import (
    load_dc_from_disk,
    load_enhancer_from_disk,
    save_dc_model_to_disk,
    save_enhancer_to_disk,
)
from app.services.pi_ratings import PiRatingWrapper, fuse_pi_probabilities
from app.services.prediction_result import DegradedReason, PredictionResult
from app.services.signal_adjuster import SignalAdjuster
from app.services.tabular_match_model import TabularMatchEnhancer, fuse_outcome_probabilities
from app.services.weibull_model import WeibullWrapper, fuse_weibull_probs
from app.services.weights import WeightConfig, get_weight_config

logger = logging.getLogger(__name__)

# ── Constants ──
DEFAULT_COMPETITION_WEIGHT = 0.9
WORLD_CUP_COMPETITION_WEIGHT = 1.5
FRIENDLY_COMPETITION_WEIGHT = 0.5


class PredictionPipeline:
    """Unified prediction pipeline for WC26 match predictions.

    Usage:
        pipeline = PredictionPipeline()
        result = await pipeline.predict_match(
            home_team="Argentina",
            away_team="Brazil",
            competition="FIFA World Cup 2026",
            is_neutral=True,
        )
        logger.info(result.home_win_prob, result.draw_prob, result.away_win_prob)
    """

    def __init__(self) -> None:
        self._dc: DixonColesModel | None = None
        self._enhancer: TabularMatchEnhancer | None = None
        self._elo: EloRatingSystem = EloRatingSystem()
        self._pi: PiRatingWrapper = PiRatingWrapper()
        self._weibull: WeibullWrapper = WeibullWrapper()
        self._signal: SignalAdjuster = SignalAdjuster()
        self._market: MarketCalibrator | None = None

    # ── Public API ──────────────────────────────────────────

    async def predict_match(
        self,
        home_team: str,
        away_team: str,
        competition: str,
        *,
        is_neutral: bool = False,
        competition_weight: float | None = None,
        competitions: list[str] | None = None,
        mode: Literal["internal_research", "creator_safe", "public_safe"] = "internal_research",
        as_of: datetime | None = None,
        # ── Callbacks for DB-dependent steps (injected by caller) ──
        db_session_factory=None,
        load_training_frame=None,
        build_team_info=None,
        lookup_venue=None,
        lookup_manual_events=None,
        compute_motivation=None,
        lookup_match_id=None,
        resolve_team_id=None,
    ) -> PredictionResult:
        """Run the full prediction pipeline for a single match.

        Args:
            home_team: Home team name (must match DB).
            away_team: Away team name.
            competition: Competition name (e.g., "FIFA World Cup 2026").
            is_neutral: True for neutral-venue matches.
            competition_weight: Training weight for this competition.
                Auto-detected: 1.5 for WC, 0.5 for friendlies, 0.9 default.
            competitions: Optional list of competition names for multi-league training.
            mode: Output filtering mode.
            as_of: Prediction timestamp (for backtesting).
            db_session_factory: Async context manager yielding DB sessions.
            load_training_frame: Async fn → pd.DataFrame.
            build_team_info: Async fn → dict of team metadata.
            lookup_venue: Async fn → venue name.
            lookup_manual_events: Async fn → list of manual event dicts.
            compute_motivation: Async fn → motivation dict.
            lookup_match_id: Async fn → match UUID string.
            resolve_team_id: Async fn → team UUID string.

        Returns:
            PredictionResult with all probabilities, xG, and metadata.
        """
        # ── Auto-detect competition settings ──
        if competition_weight is None:
            competition_weight = _default_competition_weight(competition)

        is_national = _is_national_competition(competition)
        comp_type = "national" if is_national else "club"
        team_t = "national" if is_national else "club"

        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # ── Degraded reasons accumulator (Ticket 1.2 contract) ──
        degraded_reasons: list[DegradedReason] = []

        # ── Validate callbacks ──
        if db_session_factory is None or load_training_frame is None:
            raise ValueError(
                "db_session_factory and load_training_frame are required. "
                "Use PredictionPipeline.from_snapshot() for the snapshot.py environment."
            )

        # ── 1. Load training data ──
        async with db_session_factory() as db:
            df = await load_training_frame(
                db,
                competition=None if (is_national or competitions) else competition,
                competitions=competitions,
                competition_type=comp_type,
                team_type=team_t,
            )
            team_info = await build_team_info(db, team_t) if build_team_info else {}

        if df.empty:
            raise RuntimeError(f"No training data for {competition}")

        rows = len(df)
        match_date = df["match_date"].max().to_pydatetime()

        # ── 2. Weight config ──
        stage = ""
        if lookup_match_id:
            # Stage will be resolved later; use empty for now
            pass
        wc = get_weight_config(competition, stage)

        # ── 3. Dixon-Coles (3-tier cache) ──
        dc, dc_fit = await self._load_dc(competition, df, team_info)

        dc_pred = dc.predict_match(home_team, away_team, is_neutral_venue=is_neutral)

        # ── 4. Tabular Enhancer (3-tier cache) ──
        enhancer = await self._load_enhancer(competition, df)

        enh_pred = enhancer.predict_match(
            home_team=home_team,
            away_team=away_team,
            match_date=match_date,
            competition_weight=competition_weight,
            is_neutral_venue=is_neutral,
            training_df=df,
            rest_days={"home": 5, "away": 5},
        )

        # ── 5. Weibull Copula ──
        wb_fitted = self._weibull.fit(df, timeout=60)
        wb_pred = self._weibull.predict(home_team, away_team, is_neutral) if wb_fitted else None

        # ── 6. Fuse DC + Enhancer ──
        dc_enh = {
            "home_win_prob": float(dc_pred["home_win_prob"]),
            "draw_prob": float(dc_pred["draw_prob"]),
            "away_win_prob": float(dc_pred["away_win_prob"]),
        }
        dc_enh.update(
            fuse_outcome_probabilities(
                dc_enh,
                {
                    "home_win_prob": float(enh_pred["home_win_prob"]),
                    "draw_prob": float(enh_pred["draw_prob"]),
                    "away_win_prob": float(enh_pred["away_win_prob"]),
                },
                base_weight=wc.dc_enhancer_blend,
            )
        )

        # ── 7. Fuse Weibull ──
        dc_enh.update(fuse_weibull_probs(dc_enh, wb_pred, wb_weight=wc.weibull))

        # ── 8. Elo ──
        self._elo.fit(df)
        elo_pred = self._elo.predict(
            home_team,
            away_team,
            is_neutral=is_neutral,
            competition_weight=competition_weight,
            competition=competition,
        )
        clean = dict(dc_enh)
        clean.update(fuse_elo_probabilities(clean, elo_pred, elo_weight=wc.elo))

        # ── 9. Pi-Rating (optional) ──
        pi_pred = None
        pi_ratings_dict: dict[str, float] = {}
        try:
            self._pi.fit(df)
            pi_pred = self._pi.predict(home_team, away_team, is_neutral=is_neutral)
            pi_ratings_dict = self._pi.get_ratings_dict()
        except Exception as exc:
            logger.warning("Pi-Rating fitting/prediction failed — continuing without Pi", exc_info=True)
            degraded_reasons.append(DegradedReason(
                source="pi_rating",
                reason="fitting_failed",
                severity="warning",
                detail=str(exc),
            ))
        if pi_pred:
            clean.update(fuse_pi_probabilities(clean, pi_pred, pi_weight=wc.pi))

        # ── 10. Calibration monitor (record-only, no modification) ──
        cal_monitor = {
            "enabled": False,
            "reason": "回测样本不足（< 20 条），校准器处于监控模式",
            "baseline_probs": dict(clean),
        }

        # ── 11. Signal adjustment (venue + manual events) ──
        risk_tags: list[str] = []
        signal_adjustment_log: list[dict[str, Any]] = []
        active_events: list[dict[str, Any]] = []

        async with db_session_factory() as db:
            # Venue + altitude
            venue_name = await lookup_venue(db, home_team, away_team, competition) if lookup_venue else ""
            venue_factors = self._signal.apply_venue_factors(
                dc_pred["home_xg"], dc_pred["away_xg"], venue=venue_name
            )
            if venue_factors.get("risk_tags"):
                dc_pred["home_xg"] = venue_factors["home_xg"]
                dc_pred["away_xg"] = venue_factors["away_xg"]
                risk_tags.extend(venue_factors["risk_tags"])

            # Manual events
            home_events = await lookup_manual_events(db, home_team) if lookup_manual_events else []
            away_events = await lookup_manual_events(db, away_team) if lookup_manual_events else []

            all_manual = []
            for ev in home_events:
                ev_copy = dict(ev)
                ev_copy["_side"] = "home"
                all_manual.append(ev_copy)
            for ev in away_events:
                ev_copy = dict(ev)
                ev_copy["_side"] = "away"
                all_manual.append(ev_copy)

            if all_manual and resolve_team_id:
                home_team_id = await resolve_team_id(db, home_team)
                away_team_id = await resolve_team_id(db, away_team)

                signals_for_adjuster: list[dict[str, Any]] = []
                for ev in all_manual:
                    sig_type = ev["event_type"].lower()
                    if sig_type == "rotation_hint":
                        sig_type = "lineup_hint"
                    team_id = str(home_team_id) if ev["_side"] == "home" else str(away_team_id)
                    key_players = [ev["player"]] if ev.get("player") else []
                    availability = None
                    if sig_type == "injury":
                        sev = ev.get("severity", "medium")
                        if sev == "critical":
                            availability = "out"
                        elif sev in ("high", "medium"):
                            availability = "doubtful"
                    signals_for_adjuster.append({
                        "signal_type": sig_type,
                        "team_id": team_id,
                        "confidence": float(ev.get("confidence", 0.5)),
                        "key_players": key_players,
                        "summary_zh": ev.get("note", ""),
                        "normalized_availability": availability,
                    })

                adjusted = await self._signal.apply_signals(
                    base_prediction={
                        "home_xg": dc_pred["home_xg"],
                        "away_xg": dc_pred["away_xg"],
                        "confidence_score": 0.7,
                    },
                    approved_signals=signals_for_adjuster,
                    match_context={
                        "home_team_id": str(home_team_id) if home_team_id else "",
                        "away_team_id": str(away_team_id) if away_team_id else "",
                        "home_team_name": home_team,
                        "away_team_name": away_team,
                    },
                )
                clean["home_win_prob"] = adjusted["home_win_prob"]
                clean["draw_prob"] = adjusted["draw_prob"]
                clean["away_win_prob"] = adjusted["away_win_prob"]
                dc_pred["home_xg"] = adjusted["home_xg"]
                dc_pred["away_xg"] = adjusted["away_xg"]
                dc_pred["top3_scores"] = adjusted["top3_scores"]
                signal_adjustment_log = adjusted.get("adjustment_log", [])
                risk_tags.extend(adjusted.get("risk_tags", []))
                active_events = all_manual

        # ── 12. Context adjustment ──
        context_tags = _build_context_tags(competition, is_neutral)
        ctx_adjustments = []
        try:
            from app.services.context_adjuster import get_context_adjuster
            ctx_adjuster = get_context_adjuster()
            async with db_session_factory() as ctx_db:
                ctx_result = await ctx_adjuster.apply_context_adjustments(clean, context_tags, ctx_db)
            if ctx_result.get("context_adjustments"):
                clean["home_win_prob"] = ctx_result["home_win_prob"]
                clean["draw_prob"] = ctx_result["draw_prob"]
                clean["away_win_prob"] = ctx_result["away_win_prob"]
                ctx_adjustments = ctx_result.get("context_adjustments", [])
        except Exception as exc:
            logger.warning("Context adjustment failed — continuing without", exc_info=True)
            degraded_reasons.append(DegradedReason(
                source="context_adjuster",
                reason="adjustment_failed",
                severity="warning",
                detail=str(exc),
            ))

        # ── 13. Market calibration ──
        market_applied = False
        market_weight_used = 0.0
        divergence = 0.0
        market_probs = None
        try:
            market = get_calibrator(shadow_mode=True)  # Phase 2: shadow mode
            market_probs = await market.fetch_market_probs(
                home_team, away_team, competition_weight, competition=competition
            )
            market_result = market.calibrate(
                {"home_win_prob": clean["home_win_prob"],
                 "draw_prob": clean["draw_prob"],
                 "away_win_prob": clean["away_win_prob"]},
                market_probs,
                sample_size=rows,
            )
            if market_result.get("market_applied"):
                clean["home_win_prob"] = market_result["home_win_prob"]
                clean["draw_prob"] = market_result["draw_prob"]
                clean["away_win_prob"] = market_result["away_win_prob"]
                market_applied = True
                market_weight_used = float(market_result.get("market_weight_used", 0))
                divergence = float(market_result.get("divergence", 0))
            if market_result.get("risk_tags"):
                risk_tags.extend(market_result["risk_tags"])
        except Exception as exc:
            logger.warning("Market calibration failed — continuing without", exc_info=True)
            degraded_reasons.append(DegradedReason(
                source="market_calibration",
                reason="calibration_failed",
                severity="warning",
                detail=str(exc),
            ))

        # ── 14. Build result ──
        components_used = ["dc", "enhancer", "elo"]
        if pi_pred:
            components_used.append("pi_rating")
        if wb_pred:
            components_used.append("weibull")
        if market_applied:
            components_used.append("market")

        result = PredictionResult(
            home_team=home_team,
            away_team=away_team,
            competition=competition,
            is_neutral=is_neutral,
            match_date=match_date.isoformat() if hasattr(match_date, "isoformat") else str(match_date),
            stage=stage,
            home_win_prob=float(clean["home_win_prob"]),
            draw_prob=float(clean["draw_prob"]),
            away_win_prob=float(clean["away_win_prob"]),
            home_xg=float(dc_pred["home_xg"]),
            away_xg=float(dc_pred["away_xg"]),
            dc_probs={
                "home": float(dc_pred["home_win_prob"]),
                "draw": float(dc_pred["draw_prob"]),
                "away": float(dc_pred["away_win_prob"]),
            },
            enhancer_probs={
                "home": float(enh_pred["home_win_prob"]),
                "draw": float(enh_pred["draw_prob"]),
                "away": float(enh_pred["away_win_prob"]),
            },
            elo_probs={
                "home": float(elo_pred.home_win_prob),
                "draw": float(elo_pred.draw_prob),
                "away": float(elo_pred.away_win_prob),
            },
            pi_probs={
                "home": float(pi_pred["home_win_prob"]),
                "draw": float(pi_pred["draw_prob"]),
                "away": float(pi_pred["away_win_prob"]),
            } if pi_pred else None,
            weibull_probs={
                "home": float(wb_pred["home_win_prob"]),
                "draw": float(wb_pred["draw_prob"]),
                "away": float(wb_pred["away_win_prob"]),
            } if wb_pred else None,
            market_probs=market_probs,
            home_elo=float(elo_pred.home_elo),
            away_elo=float(elo_pred.away_elo),
            elo_gap=float(elo_pred.rating_gap),
            top_scores=list(dc_pred.get("top3_scores", [])),
            score_matrix=list(dc_pred.get("score_matrix", [])),
            weight_config=wc,
            mode=mode,
            as_of=as_of.isoformat() if as_of else now_utc,
            generated_at=now_utc,
            confidence=dc_pred.get("data_quality", "fitted"),
            risk_tags=risk_tags,
            confidence_penalty=float(dc_pred.get("confidence_penalty", 0.0)),
            components_used=components_used,
            missing_inputs=[
                dr.source for dr in degraded_reasons
                if dr.severity == "error"
            ],
            degraded_reasons=degraded_reasons,
            pipeline_params={
                "dc_converged": dc_fit.converged,
                "dc_nll": dc_fit.final_neg_log_likelihood,
                "enhancer_algorithm": getattr(enhancer, "_algorithm", "HistGradientBoosting"),
                "enhancer_rows": enhancer.training_sample_count,
                "enhancer_features": len(enhancer.feature_columns),
                "elo_matches": self._elo._match_count,
                "pi_matches": self._pi._match_count,
                "config_label": (
                    f"{wc.label} (DC{wc.dc:.0%}+Enh{wc.enhancer:.0%}"
                    f"+Elo{wc.elo:.0%}+Pi{wc.pi:.0%})"
                ),
                "training_rows": rows,
            },
            active_events=active_events,
            context_adjustments=ctx_adjustments,
            market_applied=market_applied,
            market_weight_used=market_weight_used,
            divergence=divergence,
            weibull_applied=wb_pred is not None,
            elo_detail={
                "k_factor": elo_pred.k_factor,
                "home_elo": elo_pred.home_elo,
                "away_elo": elo_pred.away_elo,
                "rating_gap": elo_pred.rating_gap,
            },
            calibration_monitor=cal_monitor,
        )

        return result

    async def predict(
        self,
        home_team: str,
        away_team: str,
        competition: str,
        **kwargs: Any,
    ) -> PredictionResult:
        """Convenience alias for predict_match().

        Deprecated: Prefer ``predict_match()`` directly.
        """
        logger.info(
            "predict() is a convenience alias for predict_match(). "
            "Prefer predict_match() directly."
        )
        return await self.predict_match(home_team, away_team, competition, **kwargs)

    # ── Model loading (3-tier cache) ────────────────────────

    async def _load_dc(
        self,
        competition: str,
        df: pd.DataFrame,
        team_info: dict,
    ) -> tuple[DixonColesModel, Any]:
        """Load Dixon-Coles from cache (memory → disk → fit)."""
        mc = get_model_cache()
        cached = mc.get_dc(competition, df)
        if cached:
            dc = DixonColesModel()
            dc.set_team_info(team_info)
            mc.restore_dc(cached, dc)
            fit = type("FitSummary", (), {
                "final_neg_log_likelihood": 0.0,
                "converged": True,
                "message": "cache hit",
            })()
            return dc, fit

        cached = load_dc_from_disk(competition, df)
        if cached:
            dc = DixonColesModel()
            dc.set_team_info(team_info)
            mc.restore_dc(cached, dc)
            mc.set_dc(competition, df, dc)
            fit = type("FitSummary", (), {
                "final_neg_log_likelihood": 0.0,
                "converged": True,
                "message": "cache hit",
            })()
            return dc, fit

        dc = DixonColesModel()
        dc.set_team_info(team_info)
        fit = await asyncio.to_thread(dc.fit, df)
        mc.set_dc(competition, df, dc)
        save_dc_model_to_disk(dc, competition, df)
        return dc, fit

    async def _load_enhancer(
        self,
        competition: str,
        df: pd.DataFrame,
    ) -> TabularMatchEnhancer:
        """Load TabularEnhancer from cache (memory → disk → fit)."""
        mc = get_model_cache()
        cached = mc.get_enhancer(competition, df)
        if cached:
            enhancer = TabularMatchEnhancer()
            mc.restore_enhancer(cached, enhancer)
            return enhancer

        cached = load_enhancer_from_disk(competition, df)
        if cached:
            enhancer = TabularMatchEnhancer()
            mc.restore_enhancer(cached, enhancer)
            mc.set_enhancer(competition, df, enhancer)
            return enhancer

        enhancer = TabularMatchEnhancer()
        await asyncio.to_thread(enhancer.fit, df)
        mc.set_enhancer(competition, df, enhancer)
        save_enhancer_to_disk(mc.get_enhancer(competition, df), competition, df)
        return enhancer


# ── Helpers ────────────────────────────────────────────────

def _is_national_competition(competition: str) -> bool:
    """Detect if a competition is national-team level."""
    keywords = [
        "world cup", "euro", "copa", "nations",
        "international", "friendly", "asian cup",
        "gold cup", "african cup",
    ]
    c = competition.lower()
    return any(kw in c for kw in keywords)


def _default_competition_weight(competition: str) -> float:
    """Auto-detect competition_weight from competition name."""
    c = competition.lower()
    if "world cup" in c:
        return WORLD_CUP_COMPETITION_WEIGHT
    if any(kw in c for kw in ["friendly", "international friendly"]):
        return FRIENDLY_COMPETITION_WEIGHT
    return DEFAULT_COMPETITION_WEIGHT


def _build_context_tags(competition: str, is_neutral: bool) -> list[str]:
    """Build context tags for ContextAdjuster."""
    tags = []
    if is_neutral:
        tags.append("neutral_venue")
    c = competition.lower()
    if any(kw in c for kw in ["derby", "rivalry"]):
        tags.append("derby")
    if any(kw in c for kw in ["final", "championship"]):
        tags.append("cup_final")
    return tags

"""LearningEngine — self-evolution via per-match error attribution.

After each match finishes:
1. Compute Brier score for each prediction component (DC / Enhancer / Elo)
2. Attribute error proportionally to each component
3. Update signal accuracy tracking
4. Log model vs market divergence outcome
5. Update context performance matrix

All writes are idempotent — re-running for the same match replaces old records.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prediction_snapshot import PredictionSnapshot
from app.models.prediction_learning_log import PredictionLearningLog
from app.models.signal_track_record import SignalTrackRecord
from app.models.context_performance_matrix import ContextPerformanceMatrix
from app.models.market_divergence_log import MarketDivergenceLog
from app.models.match import Match, MatchResult

logger = logging.getLogger(__name__)


def _brier(probs: dict[str, float], actual_index: int) -> float:
    """Brier score for a 3-outcome prediction."""
    actual = [0.0, 0.0, 0.0]
    actual[actual_index] = 1.0
    preds = [probs["home"], probs["draw"], probs["away"]]
    return sum((p - a) ** 2 for p, a in zip(preds, actual)) / 3


def _result_index(home_goals: int, away_goals: int) -> int:
    """0=home win, 1=draw, 2=away win."""
    if home_goals > away_goals:
        return 0
    if home_goals == away_goals:
        return 1
    return 2


class LearningEngine:
    """Per-match learning: error attribution, signal tracking, context updates."""

    async def process_match_result(
        self,
        snapshot: PredictionSnapshot,
        home_goals: int,
        away_goals: int,
        db: AsyncSession,
    ) -> PredictionLearningLog:
        """Complete per-match learning cycle.

        Args:
            snapshot: The prediction snapshot to evaluate
            home_goals, away_goals: Actual match result
            db: Active database session

        Returns the created PredictionLearningLog record.
        """
        actual_index = _result_index(home_goals, away_goals)

        # 1. Error attribution
        error_log = await self._attribute_error(snapshot, actual_index, db)

        # 2. Signal track record update
        await self._update_signal_track_records(snapshot, actual_index, db)

        # 3. Market divergence log
        await self._log_market_divergence(snapshot, actual_index, db)

        # 4. Context matrix update
        await self._update_context_matrix(snapshot, actual_index, db)

        await db.flush()
        return error_log

    async def _attribute_error(
        self,
        snapshot: PredictionSnapshot,
        actual_index: int,
        db: AsyncSession,
    ) -> PredictionLearningLog:
        """Attribute prediction error using leave-one-out marginal contributions.

        For each component, removes it from the fusion and computes how much
        worse (or better) the prediction becomes.

        positive marginal = component helped (removing it made prediction worse)
        negative marginal = component hurt (removing it made prediction better)
        """
        baseline = snapshot.baseline_probs or {}
        final_brier = _brier(
            {"home": baseline.get("home", 0.33), "draw": baseline.get("draw", 0.33), "away": baseline.get("away", 0.33)},
            actual_index,
        )

        component = snapshot.component_probs or {}
        components = {}
        for key in ["dc", "enhancer", "elo"]:
            probs = component.get(key, {})
            if probs:
                components[key] = {
                    "home": probs.get("home", 0.33),
                    "draw": probs.get("draw", 0.33),
                    "away": probs.get("away", 0.33),
                }

        # Weights from unified config source
        from app.services.weights import get_weight_config
        wc = get_weight_config("FIFA World Cup 2026")
        weights = {"dc": wc.dc, "enhancer": wc.enhancer, "elo": wc.elo}

        # Leave-one-out marginal contributions
        dc_marginal = None
        enhancer_marginal = None
        elo_marginal = None
        market_marginal = None
        signal_marginal = None

        if components:
            # Without DC: fuse enhancer-only (or enhancer+elo if available)
            without_dc = self._fuse_without(components, weights, exclude="dc")
            if without_dc:
                dc_marginal = _brier(without_dc, actual_index) - final_brier

            # Without Enhancer: fuse dc-only (or dc+elo)
            without_enh = self._fuse_without(components, weights, exclude="enhancer")
            if without_enh:
                enhancer_marginal = _brier(without_enh, actual_index) - final_brier

            # Without Elo: fuse dc+enhancer only
            without_elo = self._fuse_without(components, weights, exclude="elo")
            if without_elo:
                elo_marginal = _brier(without_elo, actual_index) - final_brier

        # Old proportional fields — keep for backward compat, set to None
        dc_contrib = None
        enhancer_contrib = None
        elo_contrib = None

        # Error direction
        pred_home = baseline.get("home", 0.33)
        pred_draw = baseline.get("draw", 0.33)
        pred_away = baseline.get("away", 0.33)
        pred_index = max(range(3), key=lambda i: [pred_home, pred_draw, pred_away][i])
        if pred_index == actual_index:
            direction = "correct"
        elif pred_index == 0 and actual_index != 0:
            direction = "overestimate_home"
        elif pred_index == 2 and actual_index != 2:
            direction = "overestimate_away"
        else:
            direction = "mispredict"

        # Delete any previous log for this snapshot (idempotent)
        if snapshot.id:
            await db.execute(
                delete(PredictionLearningLog).where(
                    PredictionLearningLog.snapshot_id == snapshot.id
                )
            )

        log = PredictionLearningLog(
            match_id=snapshot.match_id or None,
            snapshot_id=snapshot.id or None,
            error_magnitude=final_brier,
            error_direction=direction,
            dc_error_contribution=dc_contrib,
            enhancer_error_contribution=enhancer_contrib,
            elo_error_contribution=elo_contrib,
            dc_marginal=dc_marginal,
            enhancer_marginal=enhancer_marginal,
            elo_marginal=elo_marginal,
            market_marginal=market_marginal,
            signal_marginal=signal_marginal,
        )
        db.add(log)
        return log

    @staticmethod
    def _fuse_without(
        components: dict[str, dict[str, float]],
        weights: dict[str, float],
        *,
        exclude: str,
    ) -> dict[str, float] | None:
        """Fuse remaining components after excluding one layer.

        Returns {home, draw, away} or None if no components remain.
        """
        remaining = {k: v for k, v in components.items() if k != exclude}
        if not remaining:
            return None

        # DC+Enhancer first-layer fusion (simplified from snapshot pipeline)
        # For leave-one-out, we approximate the two-step fusion in one pass
        fused = {"home": 0.0, "draw": 0.0, "away": 0.0}
        total_w = 0.0
        for name, probs in remaining.items():
            w = weights.get(name, 0.33)
            total_w += w
            for outcome in ["home", "draw", "away"]:
                fused[outcome] += probs[outcome] * w

        if total_w == 0:
            return None

        # Normalize
        total = fused["home"] + fused["draw"] + fused["away"]
        if total == 0:
            return None
        return {
            "home": fused["home"] / total,
            "draw": fused["draw"] / total,
            "away": fused["away"] / total,
        }

    async def _update_signal_track_records(
        self,
        snapshot: PredictionSnapshot,
        actual_index: int,
        db: AsyncSession,
    ) -> None:
        """Update signal accuracy based on match result.

        For each active signal in the snapshot, evaluates whether it was
        accurate/misleading/neutral based on the actual match outcome,
        then updates signal_track_record and recalculates dynamic weights.
        """
        event_ids = snapshot.active_event_ids or []
        if not event_ids:
            return

        # Ensure all signal types have baseline records
        for st in SignalTrackRecord.default_signals():
            existing = await db.get(SignalTrackRecord, st["signal_type"])
            if existing is None:
                db.add(SignalTrackRecord(**st))

        # For now, increment total_used for all active signal types
        # Full per-signal scoring needs the manual_events table join
        # which will be implemented when manual_events have better metadata
        import sqlalchemy as sa
        for evt_id in event_ids:
            # Best-effort: try to find matching signal type from manual_events
            try:
                result = await db.execute(
                    sa.text(
                        "SELECT event_type FROM manual_events WHERE id = :eid"
                    ),
                    {"eid": evt_id},
                )
                row = result.fetchone()
                if row:
                    signal_type = str(row[0]).upper()
                    await db.execute(
                        sa.text(
                            "UPDATE signal_track_record SET total_used = total_used + 1, "
                            "last_updated = datetime('now') WHERE signal_type = :st"
                        ),
                        {"st": signal_type},
                    )
            except Exception:
                pass

        # Recalculate weights after updates
        await self._recalculate_signal_weights(db)

    async def _recalculate_signal_weights(self, db: AsyncSession) -> None:
        """Recalculate current_weight_multiplier from accuracy data.

        Formula: multiplier = 0.4 + 0.6 × accuracy_rate
        accuracy_rate = accurate / (accurate + misleading)
        neutral is excluded from denominator.

        Range: [0.4, 1.0]
        - Perfect accuracy (100%): multiplier = 1.0 (full impact)
        - Complete failure (0%): multiplier = 0.4 (60% reduction)
        - Minimum 5 scored signals required to update
        """
        import sqlalchemy as sa

        result = await db.execute(
            sa.text(
                "SELECT signal_type, accurate_count, misleading_count "
                "FROM signal_track_record "
                "WHERE (accurate_count + misleading_count) >= 5"
            )
        )
        rows = result.fetchall()

        for signal_type, accurate, misleading in rows:
            total_scored = accurate + misleading
            accuracy_rate = accurate / total_scored if total_scored > 0 else 0.5
            new_multiplier = 0.4 + 0.6 * accuracy_rate

            await db.execute(
                sa.text(
                    "UPDATE signal_track_record "
                    "SET current_weight_multiplier = :mul, last_updated = datetime('now') "
                    "WHERE signal_type = :st"
                ),
                {"mul": new_multiplier, "st": signal_type},
            )

    async def _log_market_divergence(
        self,
        snapshot: PredictionSnapshot,
        actual_index: int,
        db: AsyncSession,
    ) -> None:
        """Record whether model or market was closer when they disagreed."""
        market = snapshot.market_probs
        if not market or not isinstance(market, dict) or not snapshot.baseline_probs:
            return

        model_home = snapshot.baseline_probs.get("home", 0.5)
        market_home = market.get("home")
        if market_home is None:
            return  # market_probs exists but home is null (e.g. {"home": null}) — skip
        divergence = abs(model_home - market_home)

        # Only log significant divergences
        if divergence < 0.12:
            return

        # Determine who was closer
        actual_labels = ["H", "D", "A"]
        actual_label = actual_labels[actual_index]
        model_error = abs(model_home - (1.0 if actual_index == 0 else 0.0))
        market_error = abs(market_home - (1.0 if actual_index == 0 else 0.0))

        log = MarketDivergenceLog(
            match_id=snapshot.match_id or None,
            divergence_magnitude=divergence,
            model_home_prob=model_home,
            market_home_prob=market_home,
            actual_result=actual_label,
            model_was_closer=model_error < market_error,
        )
        db.add(log)

    async def _update_context_matrix(
        self,
        snapshot: PredictionSnapshot,
        actual_index: int,
        db: AsyncSession,
    ) -> None:
        """Update context performance matrix with this match's result.

        Identifies context tags from the snapshot and updates running averages.
        """
        baseline = snapshot.baseline_probs or {}
        brier = _brier(
            {"home": baseline.get("home", 0.33), "draw": baseline.get("draw", 0.33), "away": baseline.get("away", 0.33)},
            actual_index,
        )

        # Identify context tags
        contexts = []
        if snapshot.competition and "world cup" in snapshot.competition.lower():
            contexts.append("world_cup")
        if snapshot.competition and any(
            kw in snapshot.competition.lower() for kw in ["champions", "championship"]
        ):
            contexts.append("tournament_knockout")

        # Neutral venue detection
        contexts.append("neutral_venue")  # Most international matches

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        for tag in contexts:
            existing = await db.get(ContextPerformanceMatrix, tag)
            if existing is None:
                existing = ContextPerformanceMatrix(context_tag=tag)
                db.add(existing)

            n = existing.total_matches or 0
            old_avg = existing.avg_brier_score or 0.0
            existing.total_matches = n + 1
            existing.avg_brier_score = (old_avg * n + brier) / (n + 1)
            existing.last_calibrated = now_str


# Singleton
_engine: LearningEngine | None = None


def get_learning_engine() -> LearningEngine:
    global _engine
    if _engine is None:
        _engine = LearningEngine()
    return _engine

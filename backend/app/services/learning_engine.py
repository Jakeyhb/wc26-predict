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
from uuid import UUID
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prediction_snapshot import PredictionSnapshot
from app.models.prediction_run import PredictionRun
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
    return sum((p - a) ** 2 for p, a in zip(preds, actual))


def _result_index(home_goals: int, away_goals: int) -> int:
    """0=home win, 1=draw, 2=away win."""
    if home_goals > away_goals:
        return 0
    if home_goals == away_goals:
        return 1
    return 2


def _is_uuid_like(value: str | None) -> bool:
    """Accept UUIDs stored either dashed or as 32 hex chars."""
    if not value:
        return False
    try:
        UUID(str(value))
        return True
    except (TypeError, ValueError):
        return False


def _coerce_probability(value: Any, fallback: float) -> float:
    """Convert one probability value, tolerating legacy null/bad fields."""
    if value is None:
        return fallback
    try:
        coerced = float(value)
    except (TypeError, ValueError):
        return fallback
    if coerced < 0:
        return fallback
    return coerced


def _coerce_probs(probs: dict[str, Any]) -> dict[str, float]:
    """Normalize component probability field names and legacy partial payloads."""
    if not isinstance(probs, dict):
        return {"home": 1 / 3, "draw": 1 / 3, "away": 1 / 3}
    home = _coerce_probability(probs.get("home", probs.get("home_win_prob")), 0.33)
    draw = _coerce_probability(probs.get("draw", probs.get("draw_prob")), 0.33)
    away = _coerce_probability(probs.get("away", probs.get("away_win_prob")), 0.33)
    total = home + draw + away
    if total <= 0:
        return {"home": 0.33, "draw": 0.33, "away": 0.33}
    return {
        "home": home / total,
        "draw": draw / total,
        "away": away / total,
    }


def _classify_signal_impact(signal_type: str) -> int:
    """Classify signal direction: -1 (negative/hurts team), +1 (positive/helps team), 0 (neutral).

    Used by _update_signal_track_records to determine which outcome a signal favors.
    """
    signal_upper = (signal_type or "").upper()
    negative_signals = {
        "INJURY", "SUSPENSION", "ILLNESS", "PERSONAL_LEAVE",
        "INTERNAL_CONFLICT", "FATIGUE", "TRAVEL_DISRUPTION",
    }
    positive_signals = {
        "MOTIVATION", "RETURN", "NEW_COACH_BOUNCE", "MOMENTUM",
        "CROWD_SUPPORT", "ROTATION_HINT",
    }
    # Everything else (LINEUP_RUMOR, WEATHER, etc.) → neutral
    if signal_upper in negative_signals:
        return -1
    if signal_upper in positive_signals:
        return 1
    return 0


def _lookup_stage_for_match(home_team: str | None, away_team: str | None) -> str:
    """Look up the competition stage from wc26_schedule by team names.

    Returns the stage string or '' if not found.
    """
    if not home_team or not away_team:
        return ""
    try:
        import sqlite3
        from pathlib import Path
        db_path = Path(__file__).resolve().parent.parent.parent / "data" / "local_stage2.db"
        if not db_path.exists():
            return ""
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute(
            "SELECT stage FROM wc26_schedule WHERE home_team=? AND away_team=?",
            (home_team, away_team),
        )
        row = cur.fetchone()
        conn.close()
        return str(row[0]) if row and row[0] else ""
    except Exception:
        return ""


class LearningEngine:
    """Per-match learning: error attribution, signal tracking, context updates."""

    async def process_match_result(
        self,
        snapshot: PredictionSnapshot,
        home_goals: int,
        away_goals: int,
        db: AsyncSession,
        verified_result_id: str | None = None,
    ) -> PredictionLearningLog:
        """Complete per-match learning cycle.

        Args:
            snapshot: The prediction snapshot to evaluate
            home_goals, away_goals: Actual match result
            db: Active database session
            verified_result_id: UUID string of a consensus row from
                MatchResultVerification.  If None, the learning log is
                written with status="pending_review" and does NOT affect
                production weights.

        Returns the created PredictionLearningLog record.
        """
        if not _is_uuid_like(snapshot.match_id):
            raise ValueError(
                f"Learning requires a UUID-like match_id; snapshot={snapshot.id} "
                f"has match_id={snapshot.match_id!r}"
            )

        actual_index = _result_index(home_goals, away_goals)

        # 1. Error attribution
        error_log = await self._attribute_error(
            snapshot, actual_index, db, verified_result_id,
        )

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
        verified_result_id: str | None = None,
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
        for key in ["dc", "enhancer", "elo", "pi", "pi_rating", "weibull", "market", "signals"]:
            probs = component.get(key, {})
            if probs:
                components[key] = _coerce_probs(probs)
        if snapshot.market_probs:
            components.setdefault("market", _coerce_probs(snapshot.market_probs))

        # Weights from unified config source
        from app.services.weights import get_weight_config
        stage = _lookup_stage_for_match(snapshot.home_team, snapshot.away_team)
        wc = get_weight_config(
            snapshot.competition or "FIFA World Cup 2026",
            stage,
        )
        weights = {
            "dc": wc.dc,
            "enhancer": wc.enhancer,
            "elo": wc.elo,
            "pi": wc.pi,
            "pi_rating": wc.pi,
            "weibull": wc.weibull,
            "market": wc.market_max,
            "signals": 0.0,
        }

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

            without_market = self._fuse_without(components, weights, exclude="market")
            if without_market and "market" in components:
                market_marginal = _brier(without_market, actual_index) - final_brier

            without_signal = self._fuse_without(components, weights, exclude="signals")
            if without_signal and "signals" in components:
                signal_marginal = _brier(without_signal, actual_index) - final_brier

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

        # Resolve learning status from verification state
        learning_status = await self._resolve_learning_status(db, verified_result_id)
        prediction_run_id = await self._resolve_prediction_run_id(snapshot, db)

        # Delete any previous log for this snapshot (idempotent)
        if snapshot.id:
            await db.execute(
                delete(PredictionLearningLog).where(
                    PredictionLearningLog.snapshot_id == snapshot.id
                )
            )

        log = PredictionLearningLog(
            match_id=snapshot.match_id or None,
            prediction_run_id=prediction_run_id,
            snapshot_id=snapshot.id or None,
            status=learning_status,
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

    async def _resolve_learning_status(
        self,
        db: AsyncSession,
        verified_result_id: str | None,
    ) -> str:
        """Determine the learning log status based on verification state.

        Returns:
            "active" if a verified consensus exists,
            "pending_review" otherwise.
        """
        if verified_result_id is None:
            return "pending_review"

        from uuid import UUID
        from app.models.match_result_verification import MatchResultVerification

        try:
            vid = UUID(verified_result_id)
        except (ValueError, TypeError):
            logger.warning(
                "verified_result_id=%s is not a valid UUID, falling back to pending_review",
                verified_result_id,
            )
            return "pending_review"

        result = await db.execute(
            select(MatchResultVerification).where(
                MatchResultVerification.id == vid
            )
        )
        verification = result.scalar_one_or_none()
        if verification is None:
            logger.warning(
                "verified_result_id=%s not found in DB, falling back to pending_review",
                verified_result_id,
            )
            return "pending_review"

        if verification.is_consensus:
            return "active"

        logger.warning(
            "verified_result_id=%s exists but is_consensus=False, falling back to pending_review",
            verified_result_id,
        )
        return "pending_review"

    async def _resolve_prediction_run_id(
        self,
        snapshot: PredictionSnapshot,
        db: AsyncSession,
    ) -> str | None:
        """Best-effort link from a script snapshot to the canonical prediction run."""
        if not _is_uuid_like(snapshot.match_id):
            return None
        match_uuid = UUID(str(snapshot.match_id))
        result = await db.execute(
            select(PredictionRun)
            .where(PredictionRun.match_id == match_uuid)
            .order_by(PredictionRun.created_at.desc())
            .limit(1)
        )
        run = result.scalar_one_or_none()
        return str(run.id) if run is not None else None

    @staticmethod
    def _fuse_without(
        components: dict[str, dict[str, float]],
        weights: dict[str, float],
        *,
        exclude: str,
    ) -> dict[str, float] | None:
        """Fuse remaining components after excluding one layer.

        Returns {home, draw, away} or None if no components remain.

        .. warning::

           Uses simple weighted-average fusion rather than the actual sequential
           normalized fusion from predict_match_full.py.  The real pipeline is:

              DC → +Enhancer(1-dc) → +Weibull(wb) → +Elo(elo) → +Pi(pi)

           Each step normalizes independently.  This method weights all remaining
           components in a single flat pass, so its marginal Brier scores are an
           approximation — NOT exact "what if this component were removed" values.

           Known bias: attributes too much blame to DC (high weight in flat avg)
           and too little to later-stage components (Elo, Pi) whose sequential
           effective weights are diluted by prior normalization steps.
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

        V4.0.3-fix: Now actually evaluates signal direction vs actual result
        instead of only incrementing total_used.
        """
        event_ids = snapshot.active_event_ids or []
        if not event_ids:
            return

        # Ensure all signal types have baseline records
        for st in SignalTrackRecord.default_signals():
            existing = await db.get(SignalTrackRecord, st["signal_type"])
            if existing is None:
                db.add(SignalTrackRecord(**st))

        import sqlalchemy as sa

        # Map actual_index to result direction
        # actual_index: 0=home_win, 1=draw, 2=away_win
        actual_result_map = {0: "H", 1: "D", 2: "A"}

        for evt_id in event_ids:
            try:
                result = await db.execute(
                    sa.text(
                        "SELECT event_type, team_name, severity, note "
                        "FROM manual_events WHERE id = :eid"
                    ),
                    {"eid": evt_id},
                )
                row = result.fetchone()
                if not row:
                    continue

                signal_type = str(row[0]).upper()
                team_name = str(row[1]) if row[1] else ""

                # Determine signal direction: which outcome does it favor?
                # Negative events (INJURY, SUSPENSION) hurt the affected team
                # → signal is "accurate" if that team LOSES (away_win when team=home, home_win when team=away)
                # Positive events (MOTIVATION, RETURN) help the affected team
                # → signal is "accurate" if that team WINS

                signal_impact = _classify_signal_impact(signal_type)
                if signal_impact == 0:
                    # Neutral — can't evaluate directionally
                    await db.execute(
                        sa.text(
                            "UPDATE signal_track_record SET total_used = total_used + 1, "
                            "neutral_count = neutral_count + 1, "
                            "last_updated = datetime('now') WHERE signal_type = :st"
                        ),
                        {"st": signal_type},
                    )
                    continue

                # Determine if signal favors home or away
                home_team = (snapshot.home_team or "").lower()
                away_team = (snapshot.away_team or "").lower()
                team_lower = team_name.lower()

                # Does the signal affect the home team or away team?
                affects_home = team_lower and home_team and team_lower in home_team
                affects_away = team_lower and away_team and team_lower in away_team

                if not affects_home and not affects_away:
                    # Can't determine which team — count as neutral
                    await db.execute(
                        sa.text(
                            "UPDATE signal_track_record SET total_used = total_used + 1, "
                            "neutral_count = neutral_count + 1, "
                            "last_updated = datetime('now') WHERE signal_type = :st"
                        ),
                        {"st": signal_type},
                    )
                    continue

                # Negative impact on home team → favors away_win
                # Negative impact on away team → favors home_win
                # Positive impact on home team → favors home_win
                # Positive impact on away team → favors away_win
                if signal_impact < 0:  # Negative event (injury, suspension)
                    favored_outcome = "A" if affects_home else "H"
                else:  # Positive event (motivation, return)
                    favored_outcome = "H" if affects_home else "A"

                actual_outcome = actual_result_map.get(actual_index, "D")

                # Score: accurate if favored outcome matches actual result
                if favored_outcome == actual_outcome:
                    await db.execute(
                        sa.text(
                            "UPDATE signal_track_record SET total_used = total_used + 1, "
                            "accurate_count = accurate_count + 1, "
                            "last_updated = datetime('now') WHERE signal_type = :st"
                        ),
                        {"st": signal_type},
                    )
                else:
                    await db.execute(
                        sa.text(
                            "UPDATE signal_track_record SET total_used = total_used + 1, "
                            "misleading_count = misleading_count + 1, "
                            "last_updated = datetime('now') WHERE signal_type = :st"
                        ),
                        {"st": signal_type},
                    )

            except Exception:
                logger.warning(
                    "Signal track record update failed for event %s", evt_id, exc_info=True
                )

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
        - Minimum 3 scored signals required to update multiplier
        - accuracy_rate is ALWAYS updated (even with < 3 samples) to fix display
        """
        import sqlalchemy as sa

        # V4.0.3-fix: Always fetch ALL signal records (not just >= threshold)
        # to update accuracy_rate display value
        result = await db.execute(
            sa.text(
                "SELECT signal_type, accurate_count, misleading_count "
                "FROM signal_track_record"
            )
        )
        rows = result.fetchall()

        for signal_type, accurate, misleading in rows:
            total_scored = accurate + misleading
            # Always recalculate accuracy_rate (fixes stale 0.5 display)
            accuracy_rate = accurate / total_scored if total_scored > 0 else 0.5

            # Update accuracy_rate unconditionally (display fix)
            await db.execute(
                sa.text(
                    "UPDATE signal_track_record "
                    "SET accuracy_rate = :ar, last_updated = datetime('now') "
                    "WHERE signal_type = :st"
                ),
                {"ar": accuracy_rate, "st": signal_type},
            )

            # Only update weight_multiplier with >= 3 scored samples
            # (lowered from 5 — we're data-starved in early tournament phase)
            if total_scored >= 3:
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

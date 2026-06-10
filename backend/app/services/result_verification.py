"""ResultVerificationService — verify match scores via multi-source consensus.

Pattern:
1. Callers add source claims via add_source_result()
2. build_consensus() groups by (home_goals, away_goals), checks for 2+ agreement
3. is_verified() returns whether a verified consensus exists for the match

Usage:
    service = get_verification_service()
    await service.add_source_result(db, match_id, 3, 0, "AFA", 1, "FT")
    consensus = await service.build_consensus(db, match_id)
    if consensus and consensus.is_verified:
        # Pass consensus.verification_id to LearningEngine
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match_result_verification import MatchResultVerification

logger = logging.getLogger(__name__)

# Match statuses considered "finished" for verification purposes
_FINISHED_STATUSES = frozenset({"FT", "Finished", "Final", "full_time", "finished"})


# ── source tier constants ──────────────────────────────────────────────

class SourceTier:
    """Semantic labels for source_tier values (1-6)."""
    OFFICIAL_FEDERATION = 1     # AFA, FIFA, UEFA, CONMEBOL
    OFFICIAL_COMPETITION = 2    # World Cup official site, Copa America official
    REPUTABLE_DATA_PROVIDER = 3  # API-Football, Opta, StatsBomb
    REPUTABLE_MEDIA = 4         # ESPN, BBC, Sky Sports
    AGGREGATOR = 5              # FlashScore, LiveScore
    OTHER = 6                   # Claude Code Web Search, user input


# ── dataclass ───────────────────────────────────────────────────────────

@dataclass
class ConsensusResult:
    """Result of a consensus-building operation."""
    match_id: UUID
    home_goals: int
    away_goals: int
    source_count: int
    source_names: list[str] = field(default_factory=list)
    is_verified: bool = False
    verification_id: UUID | None = None


# ── service ─────────────────────────────────────────────────────────────

class ResultVerificationService:
    """Multi-source match score verification service.

    All methods are async and operate on an AsyncSession.
    No singleton state needed — the class is stateless.
    """

    # ── public API ──────────────────────────────────────────────────

    @staticmethod
    async def add_source_result(
        db: AsyncSession,
        match_id: UUID,
        home_goals: int,
        away_goals: int,
        source_name: str,
        source_tier: int,
        match_status: str,
        notes: str | None = None,
    ) -> MatchResultVerification:
        """Record a single source's claim about a match result.

        Args:
            db: Active async database session.
            match_id: UUID of the match in the matches table.
            home_goals, away_goals: Score claimed by this source.
            source_name: Human-readable source identifier (e.g. "AFA", "ESPN").
            source_tier: 1–6 per SourceTier constants.
            match_status: Match status as reported ("FT", "Finished", etc.).
            notes: Optional free-form context.

        Returns:
            The created MatchResultVerification row.

        Raises:
            ValueError: If match_status is not a recognised finished status.
        """
        normalized_status = match_status.strip()
        if normalized_status not in _FINISHED_STATUSES:
            raise ValueError(
                f"Rejecting source claim for match {match_id}: "
                f"match_status='{match_status}' is not a finished status. "
                f"Accepted: {sorted(_FINISHED_STATUSES)}"
            )

        record = MatchResultVerification(
            match_id=match_id,
            home_goals=home_goals,
            away_goals=away_goals,
            source_name=source_name,
            source_tier=source_tier,
            match_status_at_source=normalized_status,
            is_consensus=False,
            notes=notes,
        )
        db.add(record)
        await db.flush()
        logger.info(
            "Recorded source claim: match=%s source=%s score=%d-%d status=%s",
            match_id, source_name, home_goals, away_goals, normalized_status,
        )
        return record

    @staticmethod
    async def build_consensus(
        db: AsyncSession,
        match_id: UUID,
    ) -> ConsensusResult | None:
        """Build consensus from all non-consensus source rows for this match.

        Groups source rows by (home_goals, away_goals).  If 2+ sources agree
        on the same score, creates a consensus row and links source rows to it.

        Args:
            db: Active async database session.
            match_id: UUID of the match to build consensus for.

        Returns:
            ConsensusResult if at least one source row exists, else None.
            is_verified=True only when 2+ sources agree.
        """
        # Read all non-consensus source rows for this match
        result = await db.execute(
            select(MatchResultVerification).where(
                and_(
                    MatchResultVerification.match_id == match_id,
                    MatchResultVerification.is_consensus == False,  # noqa: E712
                    MatchResultVerification.consensus_for_id.is_(None),
                )
            )
        )
        rows = list(result.scalars().all())

        if not rows:
            return None

        # Group by score
        groups: dict[tuple[int, int], list[MatchResultVerification]] = {}
        for row in rows:
            key = (row.home_goals, row.away_goals)
            groups.setdefault(key, []).append(row)

        # Find the group with the most sources
        best_group = max(groups.values(), key=len)
        best_score = (best_group[0].home_goals, best_group[0].away_goals)
        source_count = len(best_group)

        # Verified requires 2+ independent sources
        is_verified = source_count >= 2

        if not is_verified:
            source_names = sorted({r.source_name for r in best_group})
            return ConsensusResult(
                match_id=match_id,
                home_goals=best_score[0],
                away_goals=best_score[1],
                source_count=source_count,
                source_names=source_names,
                is_verified=False,
            )

        # Create consensus row
        source_names = sorted({r.source_name for r in best_group})
        consensus = MatchResultVerification(
            match_id=match_id,
            home_goals=best_score[0],
            away_goals=best_score[1],
            source_name="|".join(source_names),
            source_tier=min(r.source_tier for r in best_group),
            match_status_at_source="FT",
            is_consensus=True,
            notes=f"Consensus from {source_count} sources: {', '.join(source_names)}",
        )
        db.add(consensus)
        await db.flush()

        # Link source rows to the consensus row
        for row in best_group:
            row.consensus_for_id = consensus.id

        await db.flush()
        logger.info(
            "Consensus built: match=%s score=%d-%d sources=%d verified=True",
            match_id, best_score[0], best_score[1], source_count,
        )

        return ConsensusResult(
            match_id=match_id,
            home_goals=best_score[0],
            away_goals=best_score[1],
            source_count=source_count,
            source_names=source_names,
            is_verified=True,
            verification_id=consensus.id,
        )

    @staticmethod
    async def is_verified(
        db: AsyncSession,
        match_id: UUID,
    ) -> tuple[bool, UUID | None]:
        """Check if a verified consensus exists for this match.

        Args:
            db: Active async database session.
            match_id: UUID of the match.

        Returns:
            (True, consensus_id) if a verified consensus exists,
            (False, None) otherwise.
        """
        result = await db.execute(
            select(MatchResultVerification).where(
                and_(
                    MatchResultVerification.match_id == match_id,
                    MatchResultVerification.is_consensus == True,  # noqa: E712
                )
            ).limit(1)
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return (True, row.id)
        return (False, None)

    @staticmethod
    async def get_conflicts(
        db: AsyncSession,
        match_id: UUID,
    ) -> list[dict[str, object]]:
        """Return conflicting score claims for a match.

        A conflict exists when multiple score groups have source rows
        and no consensus has been reached yet.
        """
        result = await db.execute(
            select(MatchResultVerification).where(
                and_(
                    MatchResultVerification.match_id == match_id,
                    MatchResultVerification.is_consensus == False,  # noqa: E712
                    MatchResultVerification.consensus_for_id.is_(None),
                )
            )
        )
        rows = list(result.scalars().all())

        groups: dict[tuple[int, int], list[MatchResultVerification]] = {}
        for row in rows:
            key = (row.home_goals, row.away_goals)
            groups.setdefault(key, []).append(row)

        if len(groups) <= 1:
            return []

        return [
            {
                "score": f"{home}-{away}",
                "source_count": len(srcs),
                "sources": [s.source_name for s in srcs],
            }
            for (home, away), srcs in groups.items()
        ]


# ── singleton ───────────────────────────────────────────────────────────

_verification_service: ResultVerificationService | None = None


def get_verification_service() -> ResultVerificationService:
    """Return the singleton ResultVerificationService instance."""
    global _verification_service
    if _verification_service is None:
        _verification_service = ResultVerificationService()
    return _verification_service

from __future__ import annotations

from urllib.parse import urlparse

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger
from app.models import SourceRegistry, Team, TeamAlias
from app.utils.text import normalize_text

logger = get_logger(__name__)


class TeamResolver:
    async def resolve_team(self, team_name: str | None, db: AsyncSession) -> Team | None:
        if not team_name:
            return None

        normalized = normalize_text(team_name)
        alias_result = await db.execute(
            select(TeamAlias).where(TeamAlias.alias_normalized == normalized).limit(1)
        )
        alias = alias_result.scalar_one_or_none()
        if alias is not None:
            return await db.get(Team, alias.team_id)

        result = await db.execute(
            select(Team).where(
                or_(
                    Team.fifa_code == team_name.upper(),
                    Team.name.ilike(team_name),
                    Team.name_zh.ilike(team_name),
                )
            )
        )
        team = result.scalars().first()
        if team is not None:
            await self.ensure_aliases(team, [team_name], db, source="resolver")
        return team

    async def ensure_aliases(
        self,
        team: Team,
        aliases: list[str],
        db: AsyncSession,
        *,
        source: str,
    ) -> None:
        seen_normalized: set[str] = set()
        pending_aliases = {
            existing.alias_normalized
            for existing in db.sync_session.new
            if isinstance(existing, TeamAlias) and existing.alias_normalized
        }
        for alias in aliases:
            normalized = normalize_text(alias)
            if not normalized:
                continue
            if normalized in seen_normalized:
                continue
            if normalized in pending_aliases:
                continue
            seen_normalized.add(normalized)
            existing = await db.execute(
                select(TeamAlias).where(TeamAlias.alias_normalized == normalized).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                continue
            db.add(
                TeamAlias(
                    team_id=team.id,
                    alias=alias.strip(),
                    alias_normalized=normalized,
                    source=source,
                )
            )
            pending_aliases.add(normalized)

    async def lookup_source_reliability(self, source_url: str, db: AsyncSession) -> float:
        domain = urlparse(source_url).netloc.lower().replace("www.", "")
        result = await db.execute(select(SourceRegistry).where(SourceRegistry.domain == domain))
        source = result.scalar_one_or_none()
        return source.reliability_score if source else 0.3

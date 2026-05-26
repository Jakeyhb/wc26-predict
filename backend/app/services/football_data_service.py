from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.logging import get_logger
from app.models import IngestRun, Match, MatchResult, Team
from app.models.enums import CompetitionType, TeamType
from app.services.openfootball_service import OpenFootballService
from app.services.team_resolver import TeamResolver
from app.utils.datetime import utc_now
from app.utils.http import AsyncRateLimiter, fetch_json

settings = get_settings()
logger = get_logger(__name__)

LEAGUE_COMPETITION_CODES: dict[str, dict[str, str | float]] = {
    "PL": {"name": "Premier League", "name_zh": "英超", "weight": 0.90},
    "PD": {"name": "Primera Division", "name_zh": "西甲", "weight": 0.88},
    "BL1": {"name": "Bundesliga", "name_zh": "德甲", "weight": 0.85},
    "SA": {"name": "Serie A", "name_zh": "意甲", "weight": 0.85},
    "FL1": {"name": "Ligue 1", "name_zh": "法甲", "weight": 0.82},
    "CL": {"name": "Champions League", "name_zh": "欧冠", "weight": 1.00},
}

NATIONAL_COMPETITION_CODES: dict[str, dict[str, str | float]] = {
    "WC": {"name": "FIFA World Cup", "name_zh": "世界杯", "weight": 1.00},
    "QCAF": {"name": "WC Qualifiers CAF", "name_zh": "非洲预选", "weight": 0.70},
    "QAFC": {"name": "WC Qualifiers AFC", "name_zh": "亚洲预选", "weight": 0.70},
    "QCBL": {"name": "WC Qualifiers CONMEBOL", "name_zh": "南美预选", "weight": 0.75},
    "QCON": {"name": "WC Qualifiers CONCACAF", "name_zh": "北中美预选", "weight": 0.68},
    "QOFC": {"name": "WC Qualifiers OFC", "name_zh": "大洋洲预选", "weight": 0.60},
    "QUFA": {"name": "WC Qualifiers UEFA", "name_zh": "欧洲预选", "weight": 0.72},
    "EC": {"name": "UEFA Euro", "name_zh": "欧洲杯", "weight": 0.95},
    "WCQ": {"name": "World Cup Qualifiers", "name_zh": "世预赛", "weight": 0.70},
}

ELITE_CLUB_POOL_CODES = ("PL", "PD", "BL1", "SA", "FL1")
EUROPEAN_ELITE_POOL_CODES = ("PL", "PD", "BL1", "SA", "FL1", "CL")
CURRENT_LEAGUE_SEASON = 2025

COMPETITION_CATALOG: dict[str, dict[str, str | float]] = {
    **NATIONAL_COMPETITION_CODES,
    **LEAGUE_COMPETITION_CODES,
}


class FootballDataService:
    def __init__(self) -> None:
        self.rate_limiter = AsyncRateLimiter(min(settings.football_data_calls_per_minute, 10))
        self.team_resolver = TeamResolver()
        self.openfootball_service = OpenFootballService()

    async def fetch_competition_matches(
        self,
        competition_code: str,
        season: int | None = None,
        *,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        if not settings.football_data_api_key:
            logger.warning("FOOTBALL_DATA_API_KEY missing, skip competition fetch for %s", competition_code)
            return []
        headers = {"X-Auth-Token": settings.football_data_api_key}
        params: dict[str, Any] = {}
        if season is not None:
            params["season"] = season
        if status:
            params["status"] = status
        async with httpx.AsyncClient(base_url=settings.football_data_base_url) as client:
            try:
                await self.rate_limiter.wait()
                data = await fetch_json(
                    client,
                    f"{settings.football_data_base_url}/competitions/{competition_code}/matches",
                    headers=headers,
                    params=params,
                )
            except Exception as exc:
                logger.warning(
                    "football-data fetch failed for competition=%s season=%s status=%s, using fallback if available: %s",
                    competition_code,
                    season,
                    status,
                    exc,
                )
                return []
        return data.get("matches", [])

    async def fetch_team_squad(self, team_id: int) -> dict[str, Any]:
        if not settings.football_data_api_key:
            return {}
        async with httpx.AsyncClient(base_url=settings.football_data_base_url) as client:
            await self.rate_limiter.wait()
            return await fetch_json(
                client,
                f"{settings.football_data_base_url}/teams/{team_id}",
                headers={"X-Auth-Token": settings.football_data_api_key},
            )

    async def sync_historical_matches(self, db: AsyncSession) -> int:
        seasons = [2018, 2022]
        run = IngestRun(
            pipeline="football_data_historical",
            status="running",
            started_at=utc_now(),
            metadata_json={"competition_code": "WC", "seasons": seasons},
        )
        db.add(run)
        await db.flush()

        inserted = 0
        for season in seasons:
            matches = await self.fetch_competition_matches("WC", season)
            if matches:
                print(f"[football-data] competition=WC season={season} status=ALL matches={len(matches)}")
                for payload in matches:
                    created = await self._upsert_match_from_payload(payload, db, "WC")
                    inserted += int(created)
                    run.items_seen += 1
                logger.info("Synced WC season %s from football-data", season)
            else:
                fallback_stats = await self.openfootball_service.sync_world_cup_year(season, db)
                inserted += fallback_stats["created_matches"]
                run.items_seen += fallback_stats["source_matches"]
                logger.info("Synced WC season %s from OpenFootball fallback", season)

        run.status = "completed"
        run.finished_at = utc_now()
        run.items_inserted = inserted
        await db.commit()
        return inserted

    async def sync_league_matches(self, db: AsyncSession, seasons: list[int] | None = None) -> int:
        seasons = seasons or [2023, 2024, 2025]
        run = IngestRun(
            pipeline="football_data_leagues_historical",
            status="running",
            started_at=utc_now(),
            metadata_json={"competitions": list(LEAGUE_COMPETITION_CODES), "seasons": seasons},
        )
        db.add(run)
        await db.flush()

        inserted = 0
        for competition_index, code in enumerate(LEAGUE_COMPETITION_CODES):
            for season in seasons:
                statuses = ["FINISHED"] if season < CURRENT_LEAGUE_SEASON else ["FINISHED", "SCHEDULED"]
                for status in statuses:
                    print(
                        f"[league-sync] competition={code} season={season} status={status} starting "
                        f"(预计受 6 秒/次限流约束)"
                    )
                    matches = await self.fetch_competition_matches(code, season, status=status)
                    print(f"[league-sync] competition={code} season={season} status={status} fetched={len(matches)}")
                    for match_index, payload in enumerate(matches, start=1):
                        created = await self._upsert_match_from_payload(payload, db, code)
                        inserted += int(created)
                        run.items_seen += 1
                        if match_index % 25 == 0 or match_index == len(matches):
                            print(
                                f"[league-sync] competition={code} season={season} status={status} "
                                f"processed={match_index}/{len(matches)} total_inserted={inserted}"
                            )
                    await db.commit()
            if competition_index < len(LEAGUE_COMPETITION_CODES) - 1:
                print(f"[league-sync] competition switch pause for {code} -> next (10s)")
                await asyncio.sleep(10)

        run.status = "completed"
        run.finished_at = utc_now()
        run.items_inserted = inserted
        await db.commit()
        return inserted

    async def sync_upcoming_matches(self, db: AsyncSession) -> int:
        run = IngestRun(
            pipeline="football_data_upcoming",
            status="running",
            started_at=utc_now(),
            metadata_json={"competition": "WC"},
        )
        db.add(run)
        await db.flush()

        inserted = 0
        matches = await self.fetch_competition_matches("WC", 2026)
        now = utc_now()
        future_cutoff = now + timedelta(days=30)
        if matches:
            for payload in matches:
                match_date = self._parse_utc(payload.get("utcDate"))
                if match_date is None or not (now <= match_date <= future_cutoff):
                    continue
                created = await self._upsert_match_from_payload(payload, db, "WC")
                inserted += int(created)
                run.items_seen += 1
        else:
            fallback_stats = await self.openfootball_service.sync_world_cup_year(2026, db)
            inserted += fallback_stats["created_matches"]
            run.items_seen += fallback_stats["source_matches"]
        run.status = "completed"
        run.finished_at = utc_now()
        run.items_inserted = inserted
        await db.commit()
        return inserted

    async def sync_upcoming_league_matches(self, db: AsyncSession) -> dict[str, int]:
        now = utc_now()
        future_cutoff = now + timedelta(days=30)
        totals: dict[str, int] = {}
        for competition_index, code in enumerate(LEAGUE_COMPETITION_CODES):
            fetched = await self.fetch_competition_matches(code, CURRENT_LEAGUE_SEASON, status="SCHEDULED")
            inserted_for_competition = 0
            for payload in fetched:
                match_date = self._parse_utc(payload.get("utcDate"))
                if match_date is None or not (now <= match_date <= future_cutoff):
                    continue
                created = await self._upsert_match_from_payload(payload, db, code)
                inserted_for_competition += int(created)
            totals[code] = inserted_for_competition
            print(f"[league-upcoming] competition={code} inserted={inserted_for_competition}")
            await db.commit()
            if competition_index < len(LEAGUE_COMPETITION_CODES) - 1:
                await asyncio.sleep(10)
        return totals

    async def refresh_finished_scores(self, db: AsyncSession) -> int:
        updated = 0
        matches = await self.fetch_competition_matches("WC", 2026)
        if matches:
            for payload in matches:
                if payload.get("status") != "FINISHED":
                    continue
                result = await db.execute(select(Match).where(Match.external_id == f"football-data:{payload['id']}"))
                match = result.scalar_one_or_none()
                if match is None:
                    continue
                await self._upsert_match_result(match, payload, db)
                updated += 1
        else:
            fallback_stats = await self.openfootball_service.sync_world_cup_year(2026, db)
            updated += fallback_stats["updated_results"]
        await db.commit()
        return updated

    async def _upsert_match_from_payload(self, payload: Mapping[str, Any], db: AsyncSession, competition_code: str) -> bool:
        competition_meta = COMPETITION_CATALOG.get(competition_code, {})
        competition_type = self._competition_type(competition_code)
        home_team = await self._upsert_team(payload.get("homeTeam", {}), db, competition_code)
        away_team = await self._upsert_team(payload.get("awayTeam", {}), db, competition_code)
        external_id = f"football-data:{payload['id']}"

        result = await db.execute(select(Match).where(Match.external_id == external_id))
        match = result.scalar_one_or_none()
        created = match is None
        match_date = self._parse_utc(payload.get("utcDate")) or utc_now()
        stage = self._match_stage(payload)
        is_neutral = self._is_neutral_venue(payload, competition_code, stage)
        competition_name = str(competition_meta.get("name") or payload.get("competition", {}).get("name") or competition_code)

        if match is None:
            match = Match(
                external_id=external_id,
                home_team_id=home_team.id,
                away_team_id=away_team.id,
                match_date=match_date,
                competition=competition_name,
                competition_type=competition_type,
                competition_weight=self._competition_weight(competition_code),
                stage=stage,
                venue=self._match_venue(payload),
                is_neutral_venue=is_neutral,
                status=self._map_status(payload.get("status")),
            )
            db.add(match)
            await db.flush()
        else:
            match.home_team_id = home_team.id
            match.away_team_id = away_team.id
            match.match_date = match_date
            match.competition = competition_name
            match.competition_type = competition_type
            match.competition_weight = self._competition_weight(competition_code)
            match.stage = stage
            match.venue = self._match_venue(payload)
            match.is_neutral_venue = is_neutral
            match.status = self._map_status(payload.get("status"))

        if payload.get("status") == "FINISHED":
            await self._upsert_match_result(match, payload, db)
        return created

    async def _upsert_team(self, payload: Mapping[str, Any], db: AsyncSession, competition_code: str) -> Team:
        team_type = self._team_type(competition_code)
        name = str(payload.get("name") or payload.get("shortName") or "Unknown")
        resolver_key = str(payload.get("tla") or name)
        team = await self.team_resolver.resolve_team(resolver_key, db)
        if team is None:
            team = await self.team_resolver.resolve_team(name, db)

        area_name = None
        if isinstance(payload.get("area"), Mapping):
            area_name = payload.get("area", {}).get("name")

        fifa_code = payload.get("tla") if team_type == TeamType.NATIONAL else None
        if team is None:
            team = Team(
                name=name,
                name_zh=name,
                fifa_code=fifa_code,
                team_type=team_type,
                country=str(area_name) if area_name else None,
                confederation=self._infer_confederation(competition_code),
                elo_rating=1500.0,
            )
            db.add(team)
            await db.flush()
        else:
            if team.team_type != team_type:
                team.team_type = team_type
            if team_type == TeamType.NATIONAL and not team.fifa_code and payload.get("tla"):
                team.fifa_code = payload.get("tla")
            if team_type == TeamType.CLUB and not team.country and area_name:
                team.country = str(area_name)
            if not team.confederation:
                team.confederation = self._infer_confederation(competition_code)

        await self.team_resolver.ensure_aliases(
            team,
            [name, str(payload.get("shortName") or name), str(payload.get("tla") or "")],
            db,
            source="football-data",
        )
        return team

    async def _upsert_match_result(self, match: Match, payload: Mapping[str, Any], db: AsyncSession) -> None:
        score = payload.get("score", {}).get("fullTime", {})
        home_goals = int(score.get("home") or 0)
        away_goals = int(score.get("away") or 0)
        result = await db.execute(select(MatchResult).where(MatchResult.match_id == match.id))
        match_result = result.scalar_one_or_none()
        if match_result is None:
            db.add(
                MatchResult(
                    match_id=match.id,
                    home_goals=home_goals,
                    away_goals=away_goals,
                    home_xg=None,
                    away_xg=None,
                )
            )
        else:
            match_result.home_goals = home_goals
            match_result.away_goals = away_goals

    @staticmethod
    def _parse_utc(value: str | None):
        if not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    @staticmethod
    def _map_status(status: str | None) -> str:
        mapping = {
            "SCHEDULED": "scheduled",
            "TIMED": "scheduled",
            "IN_PLAY": "live",
            "PAUSED": "live",
            "EXTRA_TIME": "live",
            "PENALTY_SHOOTOUT": "live",
            "FINISHED": "finished",
            "POSTPONED": "postponed",
            "CANCELLED": "cancelled",
        }
        return mapping.get(status or "", "scheduled")

    @staticmethod
    def _competition_weight(code: str) -> float:
        meta = COMPETITION_CATALOG.get(code)
        return float(meta["weight"]) if meta else 0.4

    @staticmethod
    def _competition_type(code: str) -> CompetitionType:
        if code == "CL":
            return CompetitionType.CUP
        if code in LEAGUE_COMPETITION_CODES:
            return CompetitionType.CLUB
        return CompetitionType.NATIONAL

    @staticmethod
    def _team_type(code: str) -> TeamType:
        return TeamType.CLUB if code in LEAGUE_COMPETITION_CODES else TeamType.NATIONAL

    @staticmethod
    def _infer_confederation(code: str) -> str | None:
        mapping = {
            "QCAF": "CAF",
            "QAFC": "AFC",
            "QCBL": "CONMEBOL",
            "QCON": "CONCACAF",
            "QOFC": "OFC",
            "QUFA": "UEFA",
            "WC": "FIFA",
            "EC": "UEFA",
            "PL": "UEFA",
            "PD": "UEFA",
            "BL1": "UEFA",
            "SA": "UEFA",
            "FL1": "UEFA",
            "CL": "UEFA",
        }
        return mapping.get(code)

    @staticmethod
    def competition_name_to_code(competition_name: str | None) -> str | None:
        if not competition_name:
            return None
        normalized = competition_name.strip().lower()
        for code, meta in COMPETITION_CATALOG.items():
            if str(meta["name"]).lower() == normalized or str(meta["name_zh"]).lower() == normalized:
                return code
        fuzzy_aliases = {
            "world cup": "WC",
            "世界杯": "WC",
            "euro": "EC",
            "欧洲杯": "EC",
            "premier league": "PL",
            "英超": "PL",
            "primera division": "PD",
            "la liga": "PD",
            "西甲": "PD",
            "bundesliga": "BL1",
            "德甲": "BL1",
            "serie a": "SA",
            "意甲": "SA",
            "ligue 1": "FL1",
            "法甲": "FL1",
            "champions league": "CL",
            "欧冠": "CL",
        }
        for pattern, code in fuzzy_aliases.items():
            if pattern in normalized:
                return code
        aliases = {
            "英超": "PL",
            "西甲": "PD",
            "德甲": "BL1",
            "意甲": "SA",
            "法甲": "FL1",
            "欧冠": "CL",
            "世界杯": "WC",
        }
        return aliases.get(competition_name)

    @staticmethod
    def competition_name_from_code(code: str) -> str:
        meta = COMPETITION_CATALOG.get(code)
        return str(meta["name"]) if meta else code

    @staticmethod
    def competition_name_zh(competition_name: str | None) -> str:
        code = FootballDataService.competition_name_to_code(competition_name)
        if code and (meta := COMPETITION_CATALOG.get(code)):
            return str(meta["name_zh"])
        return competition_name or "未知赛事"

    @staticmethod
    def _match_stage(payload: Mapping[str, Any]) -> str | None:
        return str(payload.get("stage") or payload.get("group") or payload.get("round") or "")[:50] or None

    @staticmethod
    def _match_venue(payload: Mapping[str, Any]) -> str | None:
        return str(payload.get("venue") or "")[:100] or None

    def _is_neutral_venue(self, payload: Mapping[str, Any], competition_code: str, stage: str | None) -> bool:
        if competition_code == "CL":
            round_name = str(payload.get("round") or "").upper()
            stage_name = (stage or "").upper()
            if round_name == "FINAL" or stage_name == "FINAL" or stage_name.endswith(" FINAL"):
                return True
            return False
        if competition_code in LEAGUE_COMPETITION_CODES:
            return False
        return True

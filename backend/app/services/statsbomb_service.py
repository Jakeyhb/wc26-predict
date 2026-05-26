from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import httpx
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.logging import get_logger
from app.models import Match, MatchResult, Player, Team
from app.models.enums import CompetitionType
from app.models.enums import TeamType
from app.services.team_resolver import TeamResolver
from app.utils.datetime import utc_now
from app.utils.http import fetch_json
from app.utils.text import normalize_text

logger = get_logger(__name__)


class StatsBombService:
    base_url = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

    def __init__(self) -> None:
        self.team_resolver = TeamResolver()

    async def load_competitions(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            data = await fetch_json(client, f"{self.base_url}/competitions.json")
        return [
            item
            for item in data
            if item.get("competition_name") == "FIFA World Cup"
            and item.get("competition_gender") == "male"
            and not item.get("competition_youth")
        ]

    async def load_matches(self, competition_id: int, season_id: int) -> list[dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            return await fetch_json(client, f"{self.base_url}/matches/{competition_id}/{season_id}.json")

    async def load_events(self, match_id: int) -> list[dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            return await fetch_json(client, f"{self.base_url}/events/{match_id}.json")

    async def load_lineups(self, match_id: int) -> list[dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            return await fetch_json(client, f"{self.base_url}/lineups/{match_id}.json")

    async def extract_team_style_features(self, team_name: str, competition_id: int, season_id: int) -> dict[str, Any]:
        matches = await self.load_matches(competition_id, season_id)
        relevant_match_ids = [
            match["match_id"]
            for match in matches
            if team_name in {match["home_team"]["home_team_name"], match["away_team"]["away_team_name"]}
        ]
        if not relevant_match_ids:
            return {"team_name": team_name, "competition": competition_id, "season": season_id, "features": {}}

        aggregates = defaultdict(float)
        match_count = 0
        for match_id in relevant_match_ids:
            events = await self.load_events(match_id)
            match_count += 1
            aggregates["avg_shots_per_game"] += sum(
                1 for event in events if event.get("team", {}).get("name") == team_name and event.get("type", {}).get("name") == "Shot"
            )
            aggregates["avg_shots_on_target"] += sum(
                1
                for event in events
                if event.get("team", {}).get("name") == team_name
                and event.get("type", {}).get("name") == "Shot"
                and event.get("shot", {}).get("outcome", {}).get("name") in {"Saved", "Goal"}
            )
            team_xg = sum(
                float(event.get("shot", {}).get("statsbomb_xg", 0.0) or 0.0)
                for event in events
                if event.get("team", {}).get("name") == team_name and event.get("type", {}).get("name") == "Shot"
            )
            opp_xg = sum(
                float(event.get("shot", {}).get("statsbomb_xg", 0.0) or 0.0)
                for event in events
                if event.get("team", {}).get("name") != team_name and event.get("type", {}).get("name") == "Shot"
            )
            set_piece_shots = sum(
                1
                for event in events
                if event.get("team", {}).get("name") == team_name
                and event.get("type", {}).get("name") == "Shot"
                and event.get("play_pattern", {}).get("name") in {"From Corner", "From Free Kick", "From Throw In"}
            )
            defensive_actions = sum(
                1
                for event in events
                if event.get("team", {}).get("name") == team_name
                and event.get("type", {}).get("name") in {"Pressure", "Interception", "Ball Recovery", "Duel"}
                and (event.get("location") or [0])[0] >= 60
            )
            team_shots = max(1, sum(
                1 for event in events if event.get("team", {}).get("name") == team_name and event.get("type", {}).get("name") == "Shot"
            ))
            aggregates["avg_xg"] += team_xg
            aggregates["avg_xga"] += opp_xg
            aggregates["set_piece_threat"] += set_piece_shots / team_shots
            aggregates["pressing_intensity"] += defensive_actions / 90.0

        features = {
            key: round(value / match_count, 4)
            for key, value in aggregates.items()
        }
        return {
            "team_name": team_name,
            "competition": competition_id,
            "season": season_id,
            "features": features,
        }

    async def build_training_dataset(self) -> pd.DataFrame:
        competitions = await self.load_competitions()
        target_seasons = [item for item in competitions if item["season_name"] in {"2018", "2022"}]
        rows: list[dict[str, Any]] = []
        for competition in target_seasons:
            matches = await self.load_matches(competition["competition_id"], competition["season_id"])
            for match in matches:
                events = await self.load_events(match["match_id"])
                home_team = match["home_team"]["home_team_name"]
                away_team = match["away_team"]["away_team_name"]
                home_xg = sum(
                    float(event.get("shot", {}).get("statsbomb_xg", 0.0) or 0.0)
                    for event in events
                    if event.get("team", {}).get("name") == home_team and event.get("type", {}).get("name") == "Shot"
                )
                away_xg = sum(
                    float(event.get("shot", {}).get("statsbomb_xg", 0.0) or 0.0)
                    for event in events
                    if event.get("team", {}).get("name") == away_team and event.get("type", {}).get("name") == "Shot"
                )
                rows.append(
                    {
                        "match_date": match["match_date"],
                        "home_team": home_team,
                        "away_team": away_team,
                        "home_goals": match["home_score"],
                        "away_goals": match["away_score"],
                        "competition_weight": 1.0,
                        "is_neutral_venue": True,
                        "home_xg": home_xg,
                        "away_xg": away_xg,
                    }
                )
        dataset = pd.DataFrame(
            rows,
            columns=[
                "match_date",
                "home_team",
                "away_team",
                "home_goals",
                "away_goals",
                "competition_weight",
                "is_neutral_venue",
                "home_xg",
                "away_xg",
            ],
        )
        if dataset.empty:
            return dataset
        dataset["match_date"] = pd.to_datetime(dataset["match_date"], utc=True)
        return dataset.sort_values("match_date").reset_index(drop=True)

    async def backfill_match_result_xg(self, db: AsyncSession, dataset: pd.DataFrame) -> dict[str, int]:
        if dataset.empty:
            return {"matched": 0, "updated": 0, "skipped": 0}

        home_team = aliased(Team)
        away_team = aliased(Team)
        result = await db.execute(
            select(Match, MatchResult, home_team.name, away_team.name)
            .join(MatchResult, MatchResult.match_id == Match.id)
            .join(home_team, home_team.id == Match.home_team_id)
            .join(away_team, away_team.id == Match.away_team_id)
            .where(Match.competition.ilike("%World Cup%"))
        )

        match_lookup: dict[tuple[str, str, str], list[MatchResult]] = defaultdict(list)
        for match, match_result, home_name, away_name in result.all():
            key = (
                match.match_date.astimezone(UTC).date().isoformat(),
                normalize_text(home_name),
                normalize_text(away_name),
            )
            match_lookup[key].append(match_result)

        matched = 0
        updated = 0
        skipped = 0
        for row in dataset.itertuples(index=False):
            match_date = pd.Timestamp(row.match_date).to_pydatetime().astimezone(UTC).date().isoformat()
            key = (match_date, normalize_text(str(row.home_team)), normalize_text(str(row.away_team)))
            candidates = match_lookup.get(key, [])
            if len(candidates) != 1:
                skipped += 1
                continue
            matched += 1
            match_result = candidates[0]
            home_xg = float(row.home_xg) if row.home_xg is not None else None
            away_xg = float(row.away_xg) if row.away_xg is not None else None
            if match_result.home_xg != home_xg or match_result.away_xg != away_xg:
                match_result.home_xg = home_xg
                match_result.away_xg = away_xg
                updated += 1

        await db.commit()
        logger.info(
            "StatsBomb xG backfill matched=%s updated=%s skipped=%s",
            matched,
            updated,
            skipped,
        )
        return {"matched": matched, "updated": updated, "skipped": skipped}

    async def sync_historical_world_cup(self, db: AsyncSession) -> tuple[int, int]:
        competitions = await self.load_competitions()
        target_seasons = [item for item in competitions if item["season_name"] in {"2018", "2022"}]
        inserted_matches = 0
        inserted_teams = 0

        for competition in target_seasons:
            matches = await self.load_matches(competition["competition_id"], competition["season_id"])
            for match_payload in matches:
                home_team, home_created = await self._upsert_team(match_payload["home_team"]["home_team_name"], db)
                away_team, away_created = await self._upsert_team(match_payload["away_team"]["away_team_name"], db)
                inserted_teams += int(home_created) + int(away_created)
                external_id = f"statsbomb:{match_payload['match_id']}"
                result = await db.execute(select(Match).where(Match.external_id == external_id))
                match = result.scalar_one_or_none()
                if match is None:
                    match = Match(
                        external_id=external_id,
                        home_team_id=home_team.id,
                        away_team_id=away_team.id,
                        match_date=pd.to_datetime(match_payload["match_date"], utc=True).to_pydatetime(),
                        competition="FIFA World Cup",
                        competition_type=CompetitionType.NATIONAL,
                        competition_weight=1.0,
                        stage=match_payload.get("competition_stage", {}).get("name"),
                        venue=match_payload.get("stadium", {}).get("name"),
                        is_neutral_venue=True,
                        status="finished",
                    )
                    db.add(match)
                    await db.flush()
                    inserted_matches += 1
                else:
                    match.competition_type = CompetitionType.NATIONAL
                existing_result = await db.execute(select(MatchResult).where(MatchResult.match_id == match.id))
                if existing_result.scalar_one_or_none() is None:
                    events = await self.load_events(match_payload["match_id"])
                    home_xg = sum(
                        float(event.get("shot", {}).get("statsbomb_xg", 0.0) or 0.0)
                        for event in events
                        if event.get("team", {}).get("name") == match_payload["home_team"]["home_team_name"]
                        and event.get("type", {}).get("name") == "Shot"
                    )
                    away_xg = sum(
                        float(event.get("shot", {}).get("statsbomb_xg", 0.0) or 0.0)
                        for event in events
                        if event.get("team", {}).get("name") == match_payload["away_team"]["away_team_name"]
                        and event.get("type", {}).get("name") == "Shot"
                    )
                    db.add(
                        MatchResult(
                            match_id=match.id,
                            home_goals=int(match_payload["home_score"]),
                            away_goals=int(match_payload["away_score"]),
                            home_xg=home_xg,
                            away_xg=away_xg,
                        )
                    )
                await self._sync_lineups(match_payload["match_id"], home_team, away_team, db)
        await db.commit()
        return inserted_matches, inserted_teams

    async def _upsert_team(self, team_name: str, db: AsyncSession) -> tuple[Team, bool]:
        team = await self.team_resolver.resolve_team(team_name, db)
        if team is not None:
            team.team_type = TeamType.NATIONAL
            await self.team_resolver.ensure_aliases(team, [team_name], db, source="statsbomb")
            return team, False
        team = Team(name=team_name, name_zh=team_name, team_type=TeamType.NATIONAL, elo_rating=1500.0)
        db.add(team)
        await db.flush()
        await self.team_resolver.ensure_aliases(team, [team_name], db, source="statsbomb")
        return team, True

    async def _sync_lineups(self, match_id: int, home_team: Team, away_team: Team, db: AsyncSession) -> None:
        try:
            lineups = await self.load_lineups(match_id)
        except Exception as exc:
            logger.warning("Failed to load StatsBomb lineups for match %s: %s", match_id, exc)
            return

        team_lookup = {
            lineup["team_name"]: home_team if lineup["team_name"] == home_team.name else away_team
            for lineup in lineups
        }
        for lineup in lineups:
            team = team_lookup.get(lineup["team_name"])
            if team is None:
                continue
            for player_payload in lineup.get("lineup", []):
                exists = await db.execute(
                    select(Player).where(Player.team_id == team.id, Player.name == player_payload["player_name"]).limit(1)
                )
                if exists.scalar_one_or_none() is not None:
                    continue
                positions = player_payload.get("positions") or [{}]
                db.add(
                    Player(
                        team_id=team.id,
                        name=player_payload["player_name"],
                        name_zh=player_payload["player_name"],
                        position=str(positions[0].get("position", "UNK"))[:20],
                        is_key_player=bool(player_payload.get("jersey_number", 99) <= 11),
                        current_club=None,
                    )
                )

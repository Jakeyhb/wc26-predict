#!/usr/bin/env python3
"""Sync league standings from football-data.org and generate motivation tags.

Usage:
    python scripts/sync_standings.py                  # all supported leagues
    python scripts/sync_standings.py --league PL      # single league
    python scripts/sync_standings.py --generate-motivation  # also gen motivation events
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from app.database import AsyncSessionLocal
from app.models.standings import Standing
from app.models.motivation_event import MotivationEvent, MOTIVATION_TAGS
from app.models.match import Match
from app.models.team import Team
from app.models.enums import MatchStatus
from app.config import get_settings

settings = get_settings()

# Leagues to sync (competition codes)
SUPPORTED_LEAGUES = ["PL", "PD", "BL1", "SA", "FL1"]
SEASON = "2025"  # 2025-26 season just ended


async def fetch_standings(league_code: str) -> list[dict[str, Any]]:
    """Fetch standings from football-data.org v4 API."""
    if not settings.football_data_api_key:
        print(f"⚠️  FOOTBALL_DATA_API_KEY missing, skipping {league_code}")
        return []

    url = f"{settings.football_data_base_url}/competitions/{league_code}/standings"
    headers = {"X-Auth-Token": settings.football_data_api_key}

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            print(f"❌ Failed to fetch standings for {league_code}: {exc}")
            return []

    rows = []
    standings_list = data.get("standings", [])

    for table in standings_list:
        group = table.get("group", None)
        for entry in table.get("table", []):
            rows.append({
                "league_code": league_code,
                "season": SEASON,
                "position": entry.get("position", 0),
                "team_name": entry["team"]["name"],
                "played": entry.get("playedGames", 0),
                "won": entry.get("won", 0),
                "drawn": entry.get("draw", 0),
                "lost": entry.get("lost", 0),
                "goals_for": entry.get("goalsFor", 0),
                "goals_against": entry.get("goalsAgainst", 0),
                "goal_diff": entry.get("goalDifference", 0),
                "points": entry.get("points", 0),
                "form": entry.get("form", None),
                "group": group,
            })

    return rows


async def save_standings(rows: list[dict[str, Any]]) -> int:
    """Upsert standings into DB. Returns count of rows saved."""
    async with AsyncSessionLocal() as db:
        count = 0
        for row in rows:
            # Check if existing
            existing = await db.execute(
                select(Standing).where(
                    Standing.competition_code == row["league_code"],
                    Standing.season == row["season"],
                    Standing.team_name == row["team_name"],
                )
            )
            existing = existing.scalar_one_or_none()

            fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            if existing:
                existing.position = row["position"]
                existing.played_games = row["played"]
                existing.won = row["won"]
                existing.drawn = row["drawn"]
                existing.lost = row["lost"]
                existing.goals_for = row["goals_for"]
                existing.goals_against = row["goals_against"]
                existing.goal_difference = row["goal_diff"]
                existing.points = row["points"]
                existing.form = row["form"]
                existing.group_name = row["group"]
                existing.fetched_at = fetched_at
            else:
                db.add(Standing(
                    competition_code=row["league_code"],
                    season=row["season"],
                    team_name=row["team_name"],
                    position=row["position"],
                    played_games=row["played"],
                    won=row["won"],
                    drawn=row["drawn"],
                    lost=row["lost"],
                    goals_for=row["goals_for"],
                    goals_against=row["goals_against"],
                    goal_difference=row["goal_diff"],
                    points=row["points"],
                    form=row["form"],
                    group_name=row["group"],
                    fetched_at=fetched_at,
                ))
            count += 1

        await db.commit()
    return count


def derive_motivation(position: int, total_teams: int, team_name: str) -> tuple[str, float, str]:
    """Derive motivation tag from league position.

    Uses 5 core tags per architecture audit.
    """
    top_cutoff = max(3, total_teams // 6)       # top ~3-4 teams
    bottom_cutoff = total_teams - 2              # bottom 3

    if position <= top_cutoff:
        tag = "HIGH_MOTIVATION"
        strength = 0.85
        explanation = f"排名第{position}/{total_teams}，争冠/欧战区"
    elif position >= bottom_cutoff:
        tag = "HIGH_MOTIVATION"
        strength = 0.90
        explanation = f"排名第{position}/{total_teams}，保级压力"
    elif position <= total_teams // 3:
        tag = "MEDIUM_MOTIVATION"
        strength = 0.60
        explanation = f"排名第{position}/{total_teams}，上游有欧战目标"
    else:
        tag = "LOW_MOTIVATION"
        strength = 0.25
        explanation = f"排名第{position}/{total_teams}，中游安全区"

    return tag, strength, explanation


async def generate_motivation_events() -> int:
    """Generate motivation events for all SCHEDULED matches.

    Requires standings data to be synced first.
    """
    async with AsyncSessionLocal() as db:
        # Get all scheduled matches with team names eagerly loaded
        result = await db.execute(
            select(Match)
            .options(selectinload(Match.home_team), selectinload(Match.away_team))
            .where(Match.status == MatchStatus.SCHEDULED)
        )
        scheduled_matches = result.scalars().all()

        if not scheduled_matches:
            print("No scheduled matches found.")
            return 0

        count = 0
        for match in scheduled_matches:
            home_name = match.home_team.name if match.home_team else None
            away_name = match.away_team.name if match.away_team else None

            for team_name in [home_name, away_name]:
                if not team_name:
                    continue

                # Find standings for this team
                standing_result = await db.execute(
                    select(Standing).where(
                        Standing.team_name.ilike(f"%{team_name}%")
                    ).order_by(Standing.fetched_at.desc()).limit(1)
                )
                standing = standing_result.scalar_one_or_none()

                if not standing:
                    continue

                # Derive motivation
                total_teams = 20  # Assume 20-team league; could be refined
                tag, strength, explanation = derive_motivation(
                    standing.position, total_teams, team_name
                )

                # Check existing
                existing = await db.execute(
                    select(MotivationEvent).where(
                        MotivationEvent.match_id == match.id,
                        MotivationEvent.team_name == team_name,
                    )
                )
                existing = existing.scalar_one_or_none()

                if existing:
                    existing.motivation_tag = tag
                    existing.motivation_strength = strength
                    existing.explanation = explanation
                    existing.source = f"standings: {standing.competition_code} {standing.season} P{standing.position}"
                else:
                    db.add(MotivationEvent(
                        match_id=match.id,
                        team_name=team_name,
                        motivation_tag=tag,
                        motivation_strength=strength,
                        explanation=explanation,
                        source=f"standings: {standing.competition_code} {standing.season} P{standing.position}",
                    ))
                count += 1

        await db.commit()
    return count


async def get_motivation_for_match(db, match_id, team_name: str) -> dict[str, Any] | None:
    """Get motivation event for a specific team in a match. Sync helper."""
    from app.models.motivation_event import MotivationEvent
    result = await db.execute(
        select(MotivationEvent).where(
            MotivationEvent.match_id == match_id,
            MotivationEvent.team_name.ilike(f"%{team_name}%"),
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        return None
    return {
        "tag": event.motivation_tag,
        "strength": event.motivation_strength,
        "explanation": event.explanation,
        "source": event.source,
    }


async def main(leagues: list[str], gen_motivation: bool = False) -> None:
    print(f"🔄 Syncing standings for: {', '.join(leagues)} (season {SEASON})")
    total = 0

    for code in leagues:
        print(f"  📊 {code}...", end=" ", flush=True)
        rows = await fetch_standings(code)
        if not rows:
            print("no data")
            continue
        saved = await save_standings(rows)
        total += saved
        print(f"{saved} rows")

    print(f"✅ Standings sync complete: {total} total rows")

    if gen_motivation:
        print("🏷️  Generating motivation events...")
        count = await generate_motivation_events()
        print(f"✅ Motivation events generated: {count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync league standings")
    parser.add_argument("--league", type=str, help="Single league code (e.g. PL)")
    parser.add_argument("--generate-motivation", action="store_true",
                        help="Also generate motivation events for upcoming matches")
    args = parser.parse_args()

    leagues = [args.league] if args.league else SUPPORTED_LEAGUES
    asyncio.run(main(leagues, args.generate_motivation))

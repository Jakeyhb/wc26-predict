#!/usr/bin/env python3
"""Populate player data from football-data.org squad endpoint.

Phase A (P2-3): 16 seeded World Cup teams, ~15+ players each.
Auto-classifies importance_level based on simple heuristics.

Usage:
    python scripts/seed_players.py --dry-run     # preview only
    python scripts/seed_players.py               # seed all 16 teams
    python scripts/seed_players.py --team 762    # single team by ID
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import AsyncSessionLocal
from app.models.team import Team
from app.models.player import Player
from app.config import get_settings
from sqlalchemy import select

settings = get_settings()

# Top 16 World Cup teams with football-data.org IDs
# Key players manually curated for Phase A
TOP16_TEAMS: dict[int, dict] = {
    762: {  # Argentina
        "key_players": [
            "Lionel Messi", "Emiliano Martínez", "Enzo Fernández",
            "Julián Álvarez", "Cristian Romero", "Alexis Mac Allister",
        ],
    },
    764: {  # Brazil
        "key_players": [
            "Vinícius Júnior", "Alisson", "Marquinhos", "Rodrygo",
            "Raphinha", "Bruno Guimarães",
        ],
    },
    773: {  # France
        "key_players": [
            "Kylian Mbappé", "Antoine Griezmann", "Mike Maignan",
            "Aurélien Tchouaméni", "William Saliba", "Ousmane Dembélé",
        ],
    },
    759: {  # Germany
        "key_players": [
            "Jamal Musiala", "Florian Wirtz", "Joshua Kimmich",
            "Antonio Rüdiger", "Kai Havertz", "Marc-André ter Stegen",
        ],
    },
    770: {  # England
        "key_players": [
            "Harry Kane", "Jude Bellingham", "Declan Rice",
            "Bukayo Saka", "Phil Foden", "John Stones",
        ],
    },
    760: {  # Spain
        "key_players": [
            "Rodri", "Pedri", "Lamine Yamal", "Dani Olmo",
            "Unai Simón", "Álvaro Morata",
        ],
    },
    765: {  # Portugal
        "key_players": [
            "Cristiano Ronaldo", "Bruno Fernandes", "Bernardo Silva",
            "Rúben Dias", "Rafael Leão", "Diogo Costa",
        ],
    },
    8601: {  # Netherlands
        "key_players": [
            "Virgil van Dijk", "Frenkie de Jong", "Cody Gakpo",
            "Memphis Depay", "Matthijs de Ligt", "Xavi Simons",
        ],
    },
    784: {  # Italy
        "key_players": [
            "Gianluigi Donnarumma", "Nicolò Barella", "Federico Chiesa",
            "Sandro Tonali", "Alessandro Bastoni", "Lorenzo Pellegrini",
        ],
    },
    805: {  # Belgium
        "key_players": [
            "Kevin De Bruyne", "Romelu Lukaku", "Thibaut Courtois",
            "Jérémy Doku", "Amadou Onana", "Youri Tielemans",
        ],
    },
    799: {  # Croatia
        "key_players": [
            "Luka Modrić", "Joško Gvardiol", "Mateo Kovačić",
            "Dominik Livaković", "Marcelo Brozović", "Andrej Kramarić",
        ],
    },
    769: {  # Uruguay
        "key_players": [
            "Federico Valverde", "Darwin Núñez", "Ronald Araújo",
            "Manuel Ugarte", "Giorgian de Arrascaeta", "José María Giménez",
        ],
    },
    8020: {  # Morocco
        "key_players": [
            "Achraf Hakimi", "Brahim Díaz", "Yassine Bounou",
            "Noussair Mazraoui", "Azzedine Ounahi", "Sofyan Amrabat",
        ],
    },
    766: {  # Japan
        "key_players": [
            "Takefusa Kubo", "Kaoru Mitoma", "Wataru Endō",
            "Daichi Kamada", "Hidemasa Morita", "Zion Suzuki",
        ],
    },
    7703: {  # USA
        "key_players": [
            "Christian Pulišić", "Weston McKennie", "Antonee Robinson",
            "Tyler Adams", "Giovanni Reyna", "Matt Turner",
        ],
    },
    7697: {  # Mexico
        "key_players": [
            "Santiago Giménez", "Edson Álvarez", "Hirving Lozano",
            "Guillermo Ochoa", "César Huerta", "Johan Vásquez",
        ],
    },
}


def classify_importance(player_name: str, position: str | None, key_list: list[str], index: int) -> str:
    """Classify player importance based on position in squad + key list."""
    if player_name in key_list:
        return "key"
    if position == "Goalkeeper" and index < 2:
        return "starter"
    if index < 8:  # first 8 non-key outfield players
        return "starter"
    if index < 16:
        return "rotation"
    return "backup"


async def seed_team(team_id: int, key_players: list[str], dry_run: bool = False) -> int:
    """Fetch squad and seed players for one team."""
    url = f"{settings.football_data_base_url}/teams/{team_id}"
    headers = {"X-Auth-Token": settings.football_data_api_key}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=headers)

    if resp.status_code != 200:
        print(f"  ❌ HTTP {resp.status_code} for team {team_id}")
        return 0

    data = resp.json()
    team_name = data.get("name", f"Team-{team_id}")
    country = data.get("area", {}).get("name", "?")
    squad = data.get("squad", [])

    if not squad:
        print(f"  ⚠️  No squad data for {team_name}")
        return 0

    async with AsyncSessionLocal() as db:
        # Find or resolve team in our DB
        team_result = await db.execute(
            select(Team).where(Team.name.ilike(f"%{team_name}%")).limit(1)
        )
        team = team_result.scalar_one_or_none()

        if not team:
            print(f"  ⚠️  Team '{team_name}' not found in DB, skipping")
            return 0

        count = 0
        for i, p in enumerate(squad):
            pname = p.get("name", "")
            position = p.get("position")
            importance = classify_importance(pname, position, key_players, i)
            status = "fit"  # default — can be overridden via manual_events

            # Check existing
            existing = await db.execute(
                select(Player).where(
                    Player.team_id == team.id,
                    Player.name == pname,
                )
            )
            if existing.scalar_one_or_none():
                continue

            if not dry_run:
                db.add(Player(
                    team_id=team.id,
                    name=pname,
                    position=position,
                    importance_level=importance,
                    status=status,
                    is_key_player=(importance == "key"),
                    source=f"football-data.org/teams/{team_id}",
                ))
            count += 1

        if not dry_run:
            await db.commit()

        label = "[DRY RUN]" if dry_run else ""
        print(f"  {label} {team_name} ({country}): {count} players (key={sum(1 for k in key_players if any(p['name']==k for p in squad))})")

    return count


async def main(dry_run: bool = False, single_team: int | None = None) -> None:
    teams = {single_team: TOP16_TEAMS[single_team]} if single_team else TOP16_TEAMS
    total = 0

    for tid, info in teams.items():
        count = await seed_team(tid, info["key_players"], dry_run=dry_run)
        total += count

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Total: {total} players across {len(teams)} teams")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed player data from football-data.org")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, don't write")
    parser.add_argument("--team", type=int, help="Seed a single team by football-data.org ID")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run, args.team))

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

from sqlalchemy import select

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import AsyncSessionLocal
from app.logging import configure_logging
from app.models import Match, Team
from app.models.enums import CompetitionType
from app.models.enums import MatchStatus
from app.models.enums import TeamType


@dataclass(frozen=True)
class TeamSeed:
    fifa_code: str
    name: str
    name_zh: str
    confederation: str


TEAM_SEEDS: list[TeamSeed] = [
    TeamSeed("USA", "United States", "美国", "CONCACAF"),
    TeamSeed("CAN", "Canada", "加拿大", "CONCACAF"),
    TeamSeed("QAT", "Qatar", "卡塔尔", "AFC"),
    TeamSeed("CRC", "Costa Rica", "哥斯达黎加", "CONCACAF"),
    TeamSeed("MEX", "Mexico", "墨西哥", "CONCACAF"),
    TeamSeed("PAN", "Panama", "巴拿马", "CONCACAF"),
    TeamSeed("NZL", "New Zealand", "新西兰", "OFC"),
    TeamSeed("CHI", "Chile", "智利", "CONMEBOL"),
    TeamSeed("ARG", "Argentina", "阿根廷", "CONMEBOL"),
    TeamSeed("PER", "Peru", "秘鲁", "CONMEBOL"),
    TeamSeed("KSA", "Saudi Arabia", "沙特阿拉伯", "AFC"),
    TeamSeed("NGA", "Nigeria", "尼日利亚", "CAF"),
    TeamSeed("BRA", "Brazil", "巴西", "CONMEBOL"),
    TeamSeed("JPN", "Japan", "日本", "AFC"),
    TeamSeed("AUS", "Australia", "澳大利亚", "AFC"),
    TeamSeed("MAR", "Morocco", "摩洛哥", "CAF"),
    TeamSeed("FRA", "France", "法国", "UEFA"),
    TeamSeed("SEN", "Senegal", "塞内加尔", "CAF"),
    TeamSeed("ECU", "Ecuador", "厄瓜多尔", "CONMEBOL"),
    TeamSeed("IRN", "Iran", "伊朗", "AFC"),
    TeamSeed("ENG", "England", "英格兰", "UEFA"),
    TeamSeed("DEN", "Denmark", "丹麦", "UEFA"),
    TeamSeed("SRB", "Serbia", "塞尔维亚", "UEFA"),
    TeamSeed("KOR", "South Korea", "韩国", "AFC"),
    TeamSeed("ESP", "Spain", "西班牙", "UEFA"),
    TeamSeed("URU", "Uruguay", "乌拉圭", "CONMEBOL"),
    TeamSeed("POL", "Poland", "波兰", "UEFA"),
    TeamSeed("AUT", "Austria", "奥地利", "UEFA"),
    TeamSeed("POR", "Portugal", "葡萄牙", "UEFA"),
    TeamSeed("SUI", "Switzerland", "瑞士", "UEFA"),
    TeamSeed("CRO", "Croatia", "克罗地亚", "UEFA"),
    TeamSeed("TUR", "Turkey", "土耳其", "UEFA"),
    TeamSeed("GER", "Germany", "德国", "UEFA"),
    TeamSeed("NED", "Netherlands", "荷兰", "UEFA"),
    TeamSeed("BEL", "Belgium", "比利时", "UEFA"),
    TeamSeed("CZE", "Czechia", "捷克", "UEFA"),
    TeamSeed("ITA", "Italy", "意大利", "UEFA"),
    TeamSeed("COL", "Colombia", "哥伦比亚", "CONMEBOL"),
    TeamSeed("HUN", "Hungary", "匈牙利", "UEFA"),
    TeamSeed("SVK", "Slovakia", "斯洛伐克", "UEFA"),
    TeamSeed("SWE", "Sweden", "瑞典", "UEFA"),
    TeamSeed("NOR", "Norway", "挪威", "UEFA"),
    TeamSeed("ROU", "Romania", "罗马尼亚", "UEFA"),
    TeamSeed("GRE", "Greece", "希腊", "UEFA"),
    TeamSeed("CIV", "Cote d'Ivoire", "科特迪瓦", "CAF"),
    TeamSeed("EGY", "Egypt", "埃及", "CAF"),
    TeamSeed("ALG", "Algeria", "阿尔及利亚", "CAF"),
    TeamSeed("CMR", "Cameroon", "喀麦隆", "CAF"),
]

GROUPS: dict[str, list[str]] = {
    "A": ["USA", "CAN", "QAT", "CRC"],
    "B": ["MEX", "PAN", "NZL", "CHI"],
    "C": ["ARG", "PER", "KSA", "NGA"],
    "D": ["BRA", "JPN", "AUS", "MAR"],
    "E": ["FRA", "SEN", "ECU", "IRN"],
    "F": ["ENG", "DEN", "SRB", "KOR"],
    "G": ["ESP", "URU", "POL", "AUT"],
    "H": ["POR", "SUI", "CRO", "TUR"],
    "I": ["GER", "NED", "BEL", "CZE"],
    "J": ["ITA", "COL", "HUN", "SVK"],
    "K": ["SWE", "NOR", "ROU", "GRE"],
    "L": ["CIV", "EGY", "ALG", "CMR"],
}

VENUES = [
    "Azteca Stadium",
    "SoFi Stadium",
    "MetLife Stadium",
    "AT&T Stadium",
    "Mercedes-Benz Stadium",
    "BC Place",
    "Estadio Akron",
    "NRG Stadium",
    "Levi's Stadium",
    "Gillette Stadium",
    "Lumen Field",
    "Hard Rock Stadium",
]


async def upsert_team(team_seed: TeamSeed) -> tuple[Team, bool]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Team).where(Team.fifa_code == team_seed.fifa_code))
        team = result.scalar_one_or_none()
        created = team is None
        if team is None:
            team = Team(
                fifa_code=team_seed.fifa_code,
                name=team_seed.name,
                name_zh=team_seed.name_zh,
                team_type=TeamType.NATIONAL,
                confederation=team_seed.confederation,
                elo_rating=1500.0,
            )
            db.add(team)
        else:
            team.name = team_seed.name
            team.name_zh = team_seed.name_zh
            team.team_type = TeamType.NATIONAL
            team.confederation = team_seed.confederation
        await db.commit()
        await db.refresh(team)
        return team, created


async def upsert_match(
    *,
    external_id: str,
    home_team_id,
    away_team_id,
    match_date: datetime,
    competition: str,
    stage: str,
    venue: str,
    status: MatchStatus = MatchStatus.SCHEDULED,
) -> bool:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Match).where(Match.external_id == external_id))
        match = result.scalar_one_or_none()
        created = match is None
        if match is None:
            match = Match(
                external_id=external_id,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                match_date=match_date,
                competition="FIFA World Cup 2026",
                competition_type=CompetitionType.NATIONAL,
                stage=stage,
                venue=venue,
                is_neutral_venue=True,
                competition_weight=1.0,
                status=status,
            )
            db.add(match)
        else:
            match.home_team_id = home_team_id
            match.away_team_id = away_team_id
            match.match_date = match_date
            match.competition = competition
            match.competition_type = CompetitionType.NATIONAL
            match.stage = stage
            match.venue = venue
            match.is_neutral_venue = True
            match.competition_weight = 1.0
            match.status = status
        await db.commit()
        return created


def group_matchups(team_codes: list[str]) -> list[tuple[int, str, str]]:
    return [
        (1, team_codes[0], team_codes[1]),
        (1, team_codes[2], team_codes[3]),
        (2, team_codes[0], team_codes[2]),
        (2, team_codes[3], team_codes[1]),
        (3, team_codes[0], team_codes[3]),
        (3, team_codes[1], team_codes[2]),
    ]


async def run() -> None:
    team_map: dict[str, Team] = {}
    created_teams = 0
    created_matches = 0

    for team_seed in TEAM_SEEDS:
        team, created = await upsert_team(team_seed)
        team_map[team_seed.fifa_code] = team
        created_teams += int(created)

    tbd_team, created = await upsert_team(TeamSeed("TBD", "TBD", "待定", "FIFA"))
    team_map["TBD"] = tbd_team
    created_teams += int(created)

    group_start = datetime(2026, 6, 11, tzinfo=UTC)
    kickoff_hours = [16, 19, 22, 0, 3]
    match_index = 0

    for group_name, teams in GROUPS.items():
        for matchday, home_code, away_code in group_matchups(teams):
            day_offset = match_index // len(kickoff_hours)
            kickoff_hour = kickoff_hours[match_index % len(kickoff_hours)]
            match_date = group_start + timedelta(days=day_offset, hours=kickoff_hour)
            external_id = f"seed_2026_group_{group_name.lower()}_{match_index + 1:02d}"
            created = await upsert_match(
                external_id=external_id,
                home_team_id=team_map[home_code].id,
                away_team_id=team_map[away_code].id,
                match_date=match_date,
                competition="FIFA World Cup 2026",
                stage=f"Group {group_name} - Matchday {matchday}",
                venue=VENUES[match_index % len(VENUES)],
            )
            created_matches += int(created)
            match_index += 1

    knockout_specs = [
        ("Round of 32", 16, datetime(2026, 6, 27, 18, tzinfo=UTC)),
        ("Round of 16", 8, datetime(2026, 7, 5, 18, tzinfo=UTC)),
        ("Quarterfinal", 4, datetime(2026, 7, 9, 19, tzinfo=UTC)),
        ("Semifinal", 2, datetime(2026, 7, 14, 19, tzinfo=UTC)),
        ("Third Place Playoff", 1, datetime(2026, 7, 18, 18, tzinfo=UTC)),
        ("Final", 1, datetime(2026, 7, 19, 19, tzinfo=UTC)),
    ]

    for stage_name, count, stage_start in knockout_specs:
        for index in range(count):
            if stage_name in {"Third Place Playoff", "Final"}:
                match_date = stage_start
            elif stage_name == "Quarterfinal":
                match_date = stage_start + timedelta(days=index // 2, hours=3 * (index % 2))
            elif stage_name == "Semifinal":
                match_date = stage_start + timedelta(days=index)
            else:
                match_date = stage_start + timedelta(days=index // 2, hours=3 * (index % 2))

            external_id = f"seed_2026_{stage_name.lower().replace(' ', '_')}_{index + 1:02d}"
            created = await upsert_match(
                external_id=external_id,
                home_team_id=team_map["TBD"].id,
                away_team_id=team_map["TBD"].id,
                match_date=match_date,
                competition="FIFA World Cup 2026",
                stage=stage_name,
                venue=VENUES[(match_index + index) % len(VENUES)],
            )
            created_matches += int(created)
        match_index += count

    total_matches = len(GROUPS) * 6 + sum(count for _, count, _ in knockout_specs)
    print(f"Inserted or updated {len(TEAM_SEEDS) + 1} teams; created {created_teams} new teams.")
    print(f"Inserted or updated {total_matches} matches; created {created_matches} new matches.")


def main() -> None:
    configure_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()

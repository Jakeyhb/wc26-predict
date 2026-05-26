"""
wc_motivation.py — World Cup group-stage motivation factor calculator.

For World Cup 2026, there are no league standings. Motivation (must-win,
advancement pressure, rotation risk) must be dynamically computed from
group-stage results.

Usage::
    from app.services.wc_motivation import compute_wc_motivation

    result = await compute_wc_motivation(db, team_name="Mexico",
                                          competition="FIFA World Cup 2026")
    # result: {"tag": "MUST_WIN", "label": "必胜", "strength": 1.0, ...}
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.motivation_event import MOTIVATION_TAGS

# ═══════════════════════════════════════════════════════════
#  WC-specific motivation mapping
# ═══════════════════════════════════════════════════════════

# 2026 World Cup: 12 groups of 4, top 2 advance + 8 best 3rd-place
# Qualification scenarios depend on:
#   - Points in group (played matches only)
#   - Remaining matches
#   - Goal difference (not yet modeled — simplified to points only)

MOTIVATION_FACTORS: dict[str, dict[str, Any]] = {
    "QUALIFIED_RELAXED": {
        "tag": "ROTATION_RISK",
        "label": "已出线（可轮换）",
        "strength": 0.8,
        "explanation": "已确保晋级，可能轮换阵容",
    },
    "LIKELY_ADVANCE": {
        "tag": "MEDIUM_MOTIVATION",
        "label": "大概率晋级",
        "strength": 1.0,
        "explanation": "形势有利，正常出战",
    },
    "NEED_RESULT": {
        "tag": "HIGH_MOTIVATION",
        "label": "需要好成绩",
        "strength": 1.15,
        "explanation": "需要拿分确保晋级",
    },
    "MUST_WIN": {
        "tag": "MUST_WIN",
        "label": "必须赢",
        "strength": 1.3,
        "explanation": "不胜即大概率出局",
    },
    "ELIMINATED": {
        "tag": "LOW_MOTIVATION",
        "label": "已淘汰",
        "strength": 0.85,
        "explanation": "已无缘晋级，战意存疑",
    },
    "MATCHDAY_1": {
        "tag": "HIGH_MOTIVATION",
        "label": "首战",
        "strength": 1.05,
        "explanation": "小组赛首轮，双方全力争胜",
    },
}


@dataclass
class GroupStanding:
    """Standing for one team in a World Cup group."""
    team_name: str
    played: int = 0
    points: int = 0
    goals_for: int = 0
    goals_against: int = 0
    max_possible_points: int = 9  # 3 matches * 3 points
    remaining_matches: int = 3

    @property
    def goal_diff(self) -> int:
        return self.goals_for - self.goals_against


async def _get_team_group(
    db: AsyncSession, team_name: str
) -> str | None:
    """Find which WC group a team belongs to.

    Queries the matches table for the team's group-stage matches
    and extracts the group name from the stage field.
    """
    result = await db.execute(
        text("""
            SELECT DISTINCT m.stage
            FROM matches m
            JOIN teams h ON m.home_team_id = h.id
            JOIN teams a ON m.away_team_id = a.id
            WHERE m.competition = 'FIFA World Cup 2026'
              AND m.stage LIKE 'Group %'
              AND (h.name = :team OR a.name = :team)
            LIMIT 1
        """),
        {"team": team_name},
    )
    row = result.fetchone()
    if not row:
        return None
    # stage looks like "Group A - Matchday 1", extract "Group A"
    stage = row[0]
    # Split on " - " and take first part
    return stage.split(" - ")[0].strip() if " - " in stage else stage.strip()


async def _get_group_teams(
    db: AsyncSession, group_name: str
) -> list[str]:
    """Get all team names in a World Cup group."""
    result = await db.execute(
        text("""
            SELECT DISTINCT t.name
            FROM matches m
            JOIN teams t ON (m.home_team_id = t.id OR m.away_team_id = t.id)
            WHERE m.competition = 'FIFA World Cup 2026'
              AND m.stage LIKE :stage_prefix
              AND t.name != 'TBD'
        """),
        {"stage_prefix": f"{group_name}%"},
    )
    return [r[0] for r in result.fetchall()]


async def _get_group_results(
    db: AsyncSession, group_name: str
) -> list[dict[str, Any]]:
    """Get all finished match results for a WC group."""
    result = await db.execute(
        text("""
            SELECT
                h.name AS home_team,
                a.name AS away_team,
                mr.home_goals,
                mr.away_goals,
                m.match_date,
                m.stage
            FROM matches m
            JOIN teams h ON m.home_team_id = h.id
            JOIN teams a ON m.away_team_id = a.id
            LEFT JOIN match_results mr ON mr.match_id = m.id
            WHERE m.competition = 'FIFA World Cup 2026'
              AND m.stage LIKE :stage_prefix
              AND m.status = 'finished'
              AND mr.home_goals IS NOT NULL
        """),
        {"stage_prefix": f"{group_name}%"},
    )
    return [dict(r._mapping) for r in result.fetchall()]


async def compute_wc_motivation(
    db: AsyncSession,
    team_name: str,
    competition: str = "FIFA World Cup 2026",
) -> dict[str, Any] | None:
    """Compute World Cup group-stage motivation factor for a team.

    Returns None if the competition is not World Cup or the team
    is not found in any group.

    Motivation factors:
        - Matchday 1: HIGH_MOTIVATION (1.05) — both teams fight hard
        - Already qualified (guaranteed top 2): ROTATION_RISK (0.8)
        - Likely advance (≥4pts after 2 games): MEDIUM_MOTIVATION (1.0)
        - Need result (1-3pts, can still qualify): HIGH_MOTIVATION (1.15)
        - Must win (0-1pt after 2 games): MUST_WIN (1.3)
        - Eliminated (0pts after 2 games, impossible to advance): LOW_MOTIVATION (0.85)
    """
    if "World Cup" not in competition:
        return None

    # Find team's group
    group_name = await _get_team_group(db, team_name)
    if not group_name:
        return None

    # Get all teams in group
    group_teams = await _get_group_teams(db, group_name)
    if team_name not in group_teams:
        return None

    # Get finished results
    results = await _get_group_results(db, group_name)

    # Calculate standings
    standings: dict[str, GroupStanding] = {
        t: GroupStanding(team_name=t) for t in group_teams
    }

    for r in results:
        home = r["home_team"]
        away = r["away_team"]
        hg = r["home_goals"]
        ag = r["away_goals"]

        if home in standings:
            standings[home].played += 1
            standings[home].goals_for += hg
            standings[home].goals_against += ag
            standings[home].remaining_matches -= 1
            standings[home].max_possible_points -= 3

        if away in standings:
            standings[away].played += 1
            standings[away].goals_for += ag
            standings[away].goals_against += hg
            standings[away].remaining_matches -= 1
            standings[away].max_possible_points -= 3

        if hg > ag and home in standings:
            standings[home].points += 3
            standings[home].max_possible_points += 3  # already deducted, add back 3
        elif ag > hg and away in standings:
            standings[away].points += 3
            standings[away].max_possible_points += 3
        else:
            if home in standings:
                standings[home].points += 1
                standings[home].max_possible_points += 1
            if away in standings:
                standings[away].points += 1
                standings[away].max_possible_points += 1

    ts = standings[team_name]

    # Determine motivation based on matchday and points
    if ts.played == 0:
        # Matchday 1 — no results yet
        return {
            "tag": MOTIVATION_FACTORS["MATCHDAY_1"]["tag"],
            "label": MOTIVATION_FACTORS["MATCHDAY_1"]["label"],
            "strength": MOTIVATION_FACTORS["MATCHDAY_1"]["strength"],
            "explanation": MOTIVATION_FACTORS["MATCHDAY_1"]["explanation"],
            "source": "wc_motivation",
            "group": group_name,
            "played": 0,
            "points": 0,
        }

    if ts.played == 2:
        # After 2 matches — compute qualification scenarios
        if ts.points >= 6:
            # 6 points = qualified
            return {
                "tag": MOTIVATION_FACTORS["QUALIFIED_RELAXED"]["tag"],
                "label": MOTIVATION_FACTORS["QUALIFIED_RELAXED"]["label"],
                "strength": MOTIVATION_FACTORS["QUALIFIED_RELAXED"]["strength"],
                "explanation": f"6分已确保晋级{group_name}",
                "source": "wc_motivation",
                "group": group_name,
                "played": 2,
                "points": ts.points,
            }
        elif ts.points >= 4:
            return {
                "tag": MOTIVATION_FACTORS["LIKELY_ADVANCE"]["tag"],
                "label": MOTIVATION_FACTORS["LIKELY_ADVANCE"]["label"],
                "strength": MOTIVATION_FACTORS["LIKELY_ADVANCE"]["strength"],
                "explanation": f"4分大概率晋级{group_name}",
                "source": "wc_motivation",
                "group": group_name,
                "played": 2,
                "points": ts.points,
            }
        elif ts.points >= 1:
            return {
                "tag": MOTIVATION_FACTORS["NEED_RESULT"]["tag"],
                "label": MOTIVATION_FACTORS["NEED_RESULT"]["label"],
                "strength": MOTIVATION_FACTORS["NEED_RESULT"]["strength"],
                "explanation": f"{ts.points}分需要末轮拿分才能晋级",
                "source": "wc_motivation",
                "group": group_name,
                "played": 2,
                "points": ts.points,
            }
        else:
            return {
                "tag": MOTIVATION_FACTORS["MUST_WIN"]["tag"],
                "label": MOTIVATION_FACTORS["MUST_WIN"]["label"],
                "strength": MOTIVATION_FACTORS["MUST_WIN"]["strength"],
                "explanation": f"0分末轮必须赢球保留晋级希望",
                "source": "wc_motivation",
                "group": group_name,
                "played": 2,
                "points": ts.points,
            }

    if ts.played == 1:
        # After 1 match — still everything to play for
        if ts.points >= 3:
            return {
                "tag": MOTIVATION_FACTORS["LIKELY_ADVANCE"]["tag"],
                "label": MOTIVATION_FACTORS["LIKELY_ADVANCE"]["label"],
                "strength": MOTIVATION_FACTORS["LIKELY_ADVANCE"]["strength"],
                "explanation": f"首轮获胜，形势有利",
                "source": "wc_motivation",
                "group": group_name,
                "played": 1,
                "points": ts.points,
            }
        elif ts.points >= 1:
            return {
                "tag": MOTIVATION_FACTORS["NEED_RESULT"]["tag"],
                "label": MOTIVATION_FACTORS["NEED_RESULT"]["label"],
                "strength": MOTIVATION_FACTORS["NEED_RESULT"]["strength"],
                "explanation": f"首轮打平，次轮需争取胜利",
                "source": "wc_motivation",
                "group": group_name,
                "played": 1,
                "points": ts.points,
            }
        else:
            return {
                "tag": MOTIVATION_FACTORS["NEED_RESULT"]["tag"],
                "label": MOTIVATION_FACTORS["NEED_RESULT"]["label"],
                "strength": MOTIVATION_FACTORS["NEED_RESULT"]["strength"],
                "explanation": f"首轮失利，次轮必须拿分",
                "source": "wc_motivation",
                "group": group_name,
                "played": 1,
                "points": ts.points,
            }

    # All 3 matches played — no motivation to compute
    return {
        "tag": "MEDIUM_MOTIVATION",
        "label": "小组赛结束",
        "strength": 1.0,
        "explanation": f"小组赛已结束，{ts.points}分",
        "source": "wc_motivation",
        "group": group_name,
        "played": ts.played,
        "points": ts.points,
    }

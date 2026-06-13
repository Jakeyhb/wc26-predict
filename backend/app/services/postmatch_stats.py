"""Post-match statistics extraction and persistence helpers."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


STATSBOMB_PROVIDER = "statsbomb_open_data"
SHOT_ON_TARGET_OUTCOMES = {"Goal", "Saved", "Saved to Post"}
YELLOW_CARD_NAMES = {"Yellow Card"}
RED_CARD_NAMES = {"Red Card", "Second Yellow"}


@dataclass(frozen=True)
class PostmatchStatsRecord:
    match_id: str
    provider: str
    source_match_id: str
    source_time: str
    available_at: str
    captured_at: str
    home_xg: float | None
    away_xg: float | None
    home_shots: int | None
    away_shots: int | None
    home_shots_on_target: int | None
    away_shots_on_target: int | None
    home_yellow_cards: int | None
    away_yellow_cards: int | None
    home_red_cards: int | None
    away_red_cards: int | None
    home_corners: int | None
    away_corners: int | None
    home_possession: float | None
    away_possession: float | None
    raw_payload: dict[str, Any]
    notes: str | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event_team(event: dict[str, Any]) -> str | None:
    team = event.get("team") or {}
    name = team.get("name")
    return str(name) if name else None


def _event_type(event: dict[str, Any]) -> str | None:
    event_type = event.get("type") or {}
    name = event_type.get("name")
    return str(name) if name else None


def _shot_xg(event: dict[str, Any]) -> float:
    shot = event.get("shot") or {}
    try:
        return float(shot.get("statsbomb_xg") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _shot_on_target(event: dict[str, Any]) -> bool:
    shot = event.get("shot") or {}
    outcome = (shot.get("outcome") or {}).get("name")
    return str(outcome) in SHOT_ON_TARGET_OUTCOMES


def _card_name(event: dict[str, Any]) -> str | None:
    for key in ("foul_committed", "bad_behaviour"):
        payload = event.get(key) or {}
        card = payload.get("card") or {}
        name = card.get("name")
        if name:
            return str(name)
    return None


def _is_corner(event: dict[str, Any]) -> bool:
    if _event_type(event) != "Pass":
        return False
    pass_payload = event.get("pass") or {}
    pass_type = pass_payload.get("type") or {}
    return pass_type.get("name") == "Corner"


def _team_counts(events: list[dict[str, Any]], team_name: str) -> dict[str, Any]:
    shots = [
        event
        for event in events
        if _event_team(event) == team_name and _event_type(event) == "Shot"
    ]
    cards = [
        _card_name(event)
        for event in events
        if _event_team(event) == team_name and _card_name(event) is not None
    ]
    return {
        "xg": round(sum(_shot_xg(event) for event in shots), 6),
        "shots": len(shots),
        "shots_on_target": sum(1 for event in shots if _shot_on_target(event)),
        "yellow_cards": sum(1 for name in cards if name in YELLOW_CARD_NAMES),
        "red_cards": sum(1 for name in cards if name in RED_CARD_NAMES),
        "corners": sum(1 for event in events if _event_team(event) == team_name and _is_corner(event)),
    }


def extract_statsbomb_team_stats(
    match_payload: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    match_id: str,
    available_at: str | None = None,
    captured_at: str | None = None,
) -> PostmatchStatsRecord:
    """Extract real team-level post-match stats from a StatsBomb event feed."""
    home_team = match_payload["home_team"]["home_team_name"]
    away_team = match_payload["away_team"]["away_team_name"]
    home = _team_counts(events, home_team)
    away = _team_counts(events, away_team)
    available = available_at or _utc_now_iso()
    captured = captured_at or _utc_now_iso()
    source_time = (
        match_payload.get("last_updated")
        or match_payload.get("last_updated_360")
        or match_payload.get("metadata", {}).get("data_version")
        or available
    )

    raw_payload = {
        "source": STATSBOMB_PROVIDER,
        "source_match_id": str(match_payload["match_id"]),
        "match_date": match_payload.get("match_date"),
        "home_team": home_team,
        "away_team": away_team,
        "home_score": match_payload.get("home_score"),
        "away_score": match_payload.get("away_score"),
        "competition_stage": (match_payload.get("competition_stage") or {}).get("name"),
        "statsbomb_last_updated": match_payload.get("last_updated"),
        "statsbomb_last_updated_360": match_payload.get("last_updated_360"),
        "event_count": len(events),
    }
    return PostmatchStatsRecord(
        match_id=match_id,
        provider=STATSBOMB_PROVIDER,
        source_match_id=str(match_payload["match_id"]),
        source_time=str(source_time),
        available_at=available,
        captured_at=captured,
        home_xg=home["xg"],
        away_xg=away["xg"],
        home_shots=home["shots"],
        away_shots=away["shots"],
        home_shots_on_target=home["shots_on_target"],
        away_shots_on_target=away["shots_on_target"],
        home_yellow_cards=home["yellow_cards"],
        away_yellow_cards=away["yellow_cards"],
        home_red_cards=home["red_cards"],
        away_red_cards=away["red_cards"],
        home_corners=home["corners"],
        away_corners=away["corners"],
        home_possession=None,
        away_possession=None,
        raw_payload=raw_payload,
        notes="StatsBomb open data does not provide official possession percentage in the event feed.",
    )


def ensure_postmatch_team_stats_table(conn: sqlite3.Connection) -> None:
    """Create the SQLite table used by local scripts if migrations have not run."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS postmatch_team_stats (
            id TEXT PRIMARY KEY,
            match_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            source_match_id TEXT NOT NULL,
            source_time TEXT NOT NULL,
            available_at TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            home_xg REAL,
            away_xg REAL,
            home_shots INTEGER,
            away_shots INTEGER,
            home_shots_on_target INTEGER,
            away_shots_on_target INTEGER,
            home_yellow_cards INTEGER,
            away_yellow_cards INTEGER,
            home_red_cards INTEGER,
            away_red_cards INTEGER,
            home_corners INTEGER,
            away_corners INTEGER,
            home_possession REAL,
            away_possession REAL,
            raw_payload TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(match_id, provider, source_match_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_postmatch_stats_match ON postmatch_team_stats(match_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_postmatch_stats_provider ON postmatch_team_stats(provider)")


def upsert_postmatch_team_stats(
    conn: sqlite3.Connection,
    record: PostmatchStatsRecord,
    *,
    sync_match_result_xg: bool = True,
) -> None:
    """Upsert a stats record and optionally sync xG into match_results."""
    payload = asdict(record)
    now = _utc_now_iso()
    payload["id"] = str(uuid.uuid4())
    payload["raw_payload"] = json.dumps(record.raw_payload, ensure_ascii=False, sort_keys=True)
    payload["updated_at"] = now
    conn.execute(
        """
        INSERT INTO postmatch_team_stats (
            id, match_id, provider, source_match_id, source_time, available_at,
            captured_at, home_xg, away_xg, home_shots, away_shots,
            home_shots_on_target, away_shots_on_target, home_yellow_cards,
            away_yellow_cards, home_red_cards, away_red_cards, home_corners,
            away_corners, home_possession, away_possession, raw_payload, notes,
            created_at, updated_at
        )
        VALUES (
            :id, :match_id, :provider, :source_match_id, :source_time, :available_at,
            :captured_at, :home_xg, :away_xg, :home_shots, :away_shots,
            :home_shots_on_target, :away_shots_on_target, :home_yellow_cards,
            :away_yellow_cards, :home_red_cards, :away_red_cards, :home_corners,
            :away_corners, :home_possession, :away_possession, :raw_payload, :notes,
            :updated_at, :updated_at
        )
        ON CONFLICT(match_id, provider, source_match_id) DO UPDATE SET
            source_time = excluded.source_time,
            available_at = excluded.available_at,
            captured_at = excluded.captured_at,
            home_xg = excluded.home_xg,
            away_xg = excluded.away_xg,
            home_shots = excluded.home_shots,
            away_shots = excluded.away_shots,
            home_shots_on_target = excluded.home_shots_on_target,
            away_shots_on_target = excluded.away_shots_on_target,
            home_yellow_cards = excluded.home_yellow_cards,
            away_yellow_cards = excluded.away_yellow_cards,
            home_red_cards = excluded.home_red_cards,
            away_red_cards = excluded.away_red_cards,
            home_corners = excluded.home_corners,
            away_corners = excluded.away_corners,
            home_possession = excluded.home_possession,
            away_possession = excluded.away_possession,
            raw_payload = excluded.raw_payload,
            notes = excluded.notes,
            updated_at = excluded.updated_at
        """,
        payload,
    )
    if sync_match_result_xg and record.home_xg is not None and record.away_xg is not None:
        conn.execute(
            """
            UPDATE match_results
            SET home_xg = ?, away_xg = ?
            WHERE REPLACE(CAST(match_id AS TEXT), '-', '') = REPLACE(CAST(? AS TEXT), '-', '')
            """,
            (record.home_xg, record.away_xg, record.match_id),
        )

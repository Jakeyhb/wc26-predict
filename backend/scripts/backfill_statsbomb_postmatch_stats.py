#!/usr/bin/env python3
"""Backfill traceable post-match team stats from StatsBomb open data.

Default mode is dry-run. `--apply` creates/updates `postmatch_team_stats` and
syncs StatsBomb xG into `match_results.home_xg/away_xg`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.postmatch_stats import (  # noqa: E402
    ensure_postmatch_team_stats_table,
    extract_statsbomb_team_stats,
    upsert_postmatch_team_stats,
)
from app.utils.text import normalize_text  # noqa: E402


DB_PATH = PROJECT_ROOT / "data" / "local_stage2.db"


@dataclass
class BackfillSummary:
    mode: str
    seasons: list[str]
    competitions_loaded: int = 0
    statsbomb_matches_seen: int = 0
    matched_internal_matches: int = 0
    stats_records_ready: int = 0
    stats_records_written: int = 0
    match_results_xg_would_update: int = 0
    match_results_xg_updated: int = 0
    skipped_no_internal_match: int = 0
    skipped_ambiguous_internal_match: int = 0
    skipped_event_fetch_error: int = 0
    created_missing_result_rows: int = 0
    backup_path: str | None = None
    examples: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: {
            "matched": [],
            "no_internal_match": [],
            "ambiguous": [],
            "event_fetch_error": [],
        }
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date_key(value: Any) -> str:
    return str(value).replace("T", " ").split(" ")[0]


def _parse_seasons(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()[0]
        > 0
    )


def _load_internal_match_lookups(conn: sqlite3.Connection) -> tuple[dict[str, str], dict[tuple[str, str, str], list[str]]]:
    rows = conn.execute(
        """
        SELECT m.id, m.external_id, m.match_date, m.competition,
               ht.name AS home_team, at.name AS away_team
        FROM matches m
        JOIN teams ht ON ht.id = m.home_team_id
        JOIN teams at ON at.id = m.away_team_id
        WHERE m.competition LIKE '%World Cup%'
        """
    ).fetchall()
    by_external: dict[str, str] = {}
    by_key: dict[tuple[str, str, str], list[str]] = {}
    for row in rows:
        match_id = str(row["id"]).replace("-", "")
        external_id = str(row["external_id"] or "")
        if external_id.startswith("statsbomb:"):
            by_external[external_id] = match_id
        key = (
            _date_key(row["match_date"]),
            normalize_text(str(row["home_team"])),
            normalize_text(str(row["away_team"])),
        )
        by_key.setdefault(key, []).append(match_id)
    return by_external, by_key


def _resolve_internal_match_id(
    match_payload: dict[str, Any],
    by_external: dict[str, str],
    by_key: dict[tuple[str, str, str], list[str]],
) -> tuple[str | None, str]:
    external_id = f"statsbomb:{match_payload['match_id']}"
    if external_id in by_external:
        return by_external[external_id], "external_id"
    key = (
        _date_key(match_payload.get("match_date")),
        normalize_text(match_payload["home_team"]["home_team_name"]),
        normalize_text(match_payload["away_team"]["away_team_name"]),
    )
    candidates = by_key.get(key, [])
    if len(candidates) == 1:
        return candidates[0], "date_team_pair"
    if len(candidates) > 1:
        return None, "ambiguous_date_team_pair"
    return None, "no_internal_match"


def _xg_would_update(conn: sqlite3.Connection, match_id: str, home_xg: float | None, away_xg: float | None) -> bool:
    if home_xg is None or away_xg is None:
        return False
    row = conn.execute(
        """
        SELECT home_xg, away_xg
        FROM match_results
        WHERE REPLACE(CAST(match_id AS TEXT), '-', '') = REPLACE(CAST(? AS TEXT), '-', '')
        """,
        (match_id,),
    ).fetchone()
    if row is None:
        return False
    return row["home_xg"] != home_xg or row["away_xg"] != away_xg


def _ensure_match_result_row(conn: sqlite3.Connection, match_id: str, match_payload: dict[str, Any]) -> bool:
    row = conn.execute(
        """
        SELECT id
        FROM match_results
        WHERE REPLACE(CAST(match_id AS TEXT), '-', '') = REPLACE(CAST(? AS TEXT), '-', '')
        """,
        (match_id,),
    ).fetchone()
    if row is not None:
        return False
    import uuid

    conn.execute(
        """
        INSERT INTO match_results (id, match_id, home_goals, away_goals)
        VALUES (?, ?, ?, ?)
        """,
        (
            uuid.uuid4().hex,
            match_id,
            int(match_payload.get("home_score") or 0),
            int(match_payload.get("away_score") or 0),
        ),
    )
    return True


def _backup_db(db_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{db_path.stem}_pre_v361_statsbomb_{timestamp}{db_path.suffix}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def _append_example(summary: BackfillSummary, bucket: str, payload: dict[str, Any]) -> None:
    if len(summary.examples[bucket]) < 10:
        summary.examples[bucket].append(payload)


async def run(
    conn: sqlite3.Connection,
    *,
    seasons: set[str],
    apply: bool,
    limit: int | None = None,
    available_at: str | None = None,
    service: Any | None = None,
) -> BackfillSummary:
    conn.row_factory = sqlite3.Row
    if service is None:
        from app.services.statsbomb_service import StatsBombService

        service = StatsBombService()
    summary = BackfillSummary(mode="APPLY" if apply else "DRY-RUN", seasons=sorted(seasons))
    by_external, by_key = _load_internal_match_lookups(conn)
    available = available_at or _utc_now_iso()
    captured = _utc_now_iso()

    competitions = await service.load_competitions()
    targets = [
        item
        for item in competitions
        if item.get("season_name") in seasons
        and item.get("competition_name") == "FIFA World Cup"
        and item.get("competition_gender") == "male"
    ]
    summary.competitions_loaded = len(targets)

    if apply:
        ensure_postmatch_team_stats_table(conn)

    processed = 0
    for competition in targets:
        matches = await service.load_matches(competition["competition_id"], competition["season_id"])
        for match_payload in matches:
            if limit is not None and processed >= limit:
                return summary
            processed += 1
            summary.statsbomb_matches_seen += 1
            internal_match_id, reason = _resolve_internal_match_id(match_payload, by_external, by_key)
            example = {
                "statsbomb_match_id": match_payload.get("match_id"),
                "date": match_payload.get("match_date"),
                "home_team": match_payload.get("home_team", {}).get("home_team_name"),
                "away_team": match_payload.get("away_team", {}).get("away_team_name"),
                "reason": reason,
            }
            if internal_match_id is None:
                if reason == "ambiguous_date_team_pair":
                    summary.skipped_ambiguous_internal_match += 1
                    _append_example(summary, "ambiguous", example)
                else:
                    summary.skipped_no_internal_match += 1
                    _append_example(summary, "no_internal_match", example)
                continue

            try:
                events = await service.load_events(int(match_payload["match_id"]))
            except Exception as exc:
                summary.skipped_event_fetch_error += 1
                _append_example(summary, "event_fetch_error", {**example, "error": str(exc)[:200]})
                continue

            record = extract_statsbomb_team_stats(
                match_payload,
                events,
                match_id=internal_match_id,
                available_at=available,
                captured_at=captured,
            )
            summary.matched_internal_matches += 1
            summary.stats_records_ready += 1
            xg_needs_update = _xg_would_update(conn, internal_match_id, record.home_xg, record.away_xg)
            if xg_needs_update:
                summary.match_results_xg_would_update += 1
            _append_example(
                summary,
                "matched",
                {
                    **example,
                    "match_id": internal_match_id,
                    "home_xg": record.home_xg,
                    "away_xg": record.away_xg,
                    "home_shots": record.home_shots,
                    "away_shots": record.away_shots,
                },
            )

            if apply:
                created_result = _ensure_match_result_row(conn, internal_match_id, match_payload)
                summary.created_missing_result_rows += int(created_result)
                upsert_postmatch_team_stats(conn, record, sync_match_result_xg=True)
                summary.stats_records_written += 1
                if xg_needs_update:
                    summary.match_results_xg_updated += 1

    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill post-match stats from StatsBomb open data.")
    parser.add_argument("--db", default=str(DB_PATH), help="SQLite database path.")
    parser.add_argument("--seasons", default="2018,2022", help="Comma-separated StatsBomb season_name values.")
    parser.add_argument("--limit", type=int, default=None, help="Limit StatsBomb matches processed.")
    parser.add_argument("--available-at", default="", help="Override available_at timestamp for imported stats.")
    parser.add_argument("--json-out", default="", help="Optional JSON summary path.")
    parser.add_argument("--apply", action="store_true", help="Write postmatch_team_stats and sync match_results xG.")
    return parser.parse_args(argv)


async def async_main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    summary = BackfillSummary(mode="APPLY" if args.apply else "DRY-RUN", seasons=sorted(_parse_seasons(args.seasons)))
    try:
        if args.apply:
            backup_path = _backup_db(db_path)
            summary.backup_path = str(backup_path)
        summary = await run(
            conn,
            seasons=_parse_seasons(args.seasons),
            apply=args.apply,
            limit=args.limit,
            available_at=args.available_at or None,
        )
        if args.apply:
            summary.backup_path = summary.backup_path or str(backup_path)
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    payload = asdict(summary)
    print("=" * 72)
    print("STATSBOMB POSTMATCH STATS BACKFILL")
    print("=" * 72)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON summary written: {out_path}")
    if not args.apply:
        print("\nNo changes written. Re-run with --apply to update the database.")
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())

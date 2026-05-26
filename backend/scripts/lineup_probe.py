#!/usr/bin/env python3
"""Probe football-data.org for lineup availability timing.

Empirically determine when lineup/bench/formation data becomes available
before kickoff. Runs probes at configured offsets from match time.

Usage:
    # Probe all upcoming matches within 48h
    python scripts/lineup_probe.py

    # Probe a specific match
    python scripts/lineup_probe.py --match-id football-data:544563

    # Run as scheduled probe (meant for cron/Celery)
    python scripts/lineup_probe.py --probe-window 72

Status (2026-05-12):
    First probe on a TIMED match (RC Celta vs Levante, T-0) showed NO lineup
    data. homeTeam only has id/name/shortName/tla/crest. Full probe can only
    execute when 2026-27 league season or World Cup warmups begin (June-July).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = BACKEND_DIR / "data" / "lineup_probes"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import AsyncSessionLocal
from app.models.match import Match
from app.models.lineup_probe_log import LineupProbeLog
from app.models.enums import MatchStatus
from app.config import get_settings

settings = get_settings()

# Probe offsets (minutes before kickoff) — for future use
PROBE_OFFSETS = [-1440, -360, -180, -90, -60, -30]  # T-24h, T-6h, T-3h, T-90m, T-60m, T-30m


async def probe_match(external_id: str, save_raw: bool = True) -> dict[str, Any]:
    """Probe a single match for lineup data via football-data.org."""
    if not settings.football_data_api_key:
        return {"error": "FOOTBALL_DATA_API_KEY missing"}

    now = datetime.now(timezone.utc)
    url = f"{settings.football_data_base_url}/matches/{external_id.split(':')[-1]}"
    headers = {"X-Auth-Token": settings.football_data_api_key}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=headers)

    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}", "body": resp.text[:200]}

    data = resp.json()
    ht = data.get("homeTeam", {})
    at = data.get("awayTeam", {})

    result = {
        "external_match_id": external_id,
        "probe_time": now.isoformat(),
        "api_match_status": data.get("status"),
        "api_last_updated": data.get("lastUpdated"),
        "has_lineup": "lineup" in ht or "lineup" in at,
        "has_bench": "bench" in ht or "bench" in at,
        "has_formation": bool(ht.get("formation") or at.get("formation")),
        "has_coach": "coach" in ht or "coach" in at,
        "home_team_keys": list(ht.keys()),
        "match_date": data.get("utcDate"),
    }

    # Calculate minutes to kickoff
    if result["match_date"]:
        kickoff = datetime.fromisoformat(result["match_date"].replace("Z", "+00:00"))
        result["minutes_to_kickoff"] = int((kickoff - now).total_seconds() / 60)
    else:
        result["minutes_to_kickoff"] = 9999

    # Save raw response
    if save_raw:
        raw_path = REPORTS_DIR / f"{external_id.replace(':', '_')}_{now.strftime('%Y%m%d_%H%M')}.json"
        raw_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        result["raw_response_path"] = str(raw_path)

    return result


async def save_probe(db, result: dict[str, Any], match_db_id=None) -> None:
    """Persist a probe result to the lineup_probe_logs table."""
    if "error" in result:
        return

    probe = LineupProbeLog(
        match_id=match_db_id,
        external_match_id=result["external_match_id"],
        probe_time=result["probe_time"],
        minutes_to_kickoff=result.get("minutes_to_kickoff", 9999),
        has_lineup=result["has_lineup"],
        has_bench=result["has_bench"],
        has_formation=result["has_formation"],
        has_coach=result["has_coach"],
        api_match_status=result["api_match_status"],
        api_last_updated=result["api_last_updated"],
        raw_response_path=result.get("raw_response_path"),
        notes=f"Home team keys: {result.get('home_team_keys', [])}",
    )
    db.add(probe)
    await db.commit()


async def run_probes(probe_window_hours: int = 48) -> list[dict[str, Any]]:
    """Run lineup probes on all upcoming matches within the window."""
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        # Find scheduled matches within window
        result = await db.execute(
            select(Match)
            .options(selectinload(Match.home_team), selectinload(Match.away_team))
            .where(
                Match.status == MatchStatus.SCHEDULED,
                Match.match_date > now,
            )
            .order_by(Match.match_date)
        )
        matches = result.scalars().all()

    # Filter by probe window
    window_end = now.timestamp() + probe_window_hours * 3600
    candidates = [
        m for m in matches
        if m.match_date and m.match_date.timestamp() <= window_end
    ]

    if not candidates:
        print(f"⚠️  No upcoming matches within {probe_window_hours}h window.")
        print(f"   Total scheduled: {len(matches)}")
        print(f"   Earliest: {matches[0].match_date if matches else 'N/A'}")
        print()
        print("   P1-3 probe deferred — no active matches to probe.")
        print("   Script is ready. Will be useful when 2026-27 season or World Cup warmups begin.")
        return []

    print(f"🔍 Probing {len(candidates)} matches within {probe_window_hours}h window...")
    results = []

    async with AsyncSessionLocal() as db:
        for m in candidates:
            ext_id = m.external_id
            home = m.home_team.name if m.home_team else "?"
            away = m.away_team.name if m.away_team else "?"
            print(f"  ⏱  {ext_id} ({home} vs {away})...", end=" ", flush=True)

            probe = await probe_match(ext_id)
            await save_probe(db, probe, match_db_id=m.id)
            results.append(probe)

            status = "✅ LINEUP" if probe.get("has_lineup") else "❌ no lineup"
            print(f"{status} (status={probe.get('api_match_status')}, keys={probe.get('home_team_keys')})")

    return results


async def show_summary() -> None:
    """Show probe history summary."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(LineupProbeLog).order_by(LineupProbeLog.probe_time.desc()).limit(20)
        )
        logs = result.scalars().all()

        if not logs:
            print("No probe logs yet.")
            return

        print(f"{'时间':<22} {'比赛ID':<25} {'T-':>6}  {'首发':<6} {'替补':<6} {'阵型':<6} {'教练':<6} {'状态':<12}")
        print("-" * 110)
        for log in logs:
            t = f"{log.minutes_to_kickoff:+d}m" if log.minutes_to_kickoff != 9999 else "?"
            print(
                f"{log.probe_time:<22} {log.external_match_id:<25} {t:>6}  "
                f"{'✅' if log.has_lineup else '❌':<6} "
                f"{'✅' if log.has_bench else '❌':<6} "
                f"{'✅' if log.has_formation else '❌':<6} "
                f"{'✅' if log.has_coach else '❌':<6} "
                f"{log.api_match_status or '?':<12}"
            )

        lineup_available = sum(1 for l in logs if l.has_lineup)
        print(f"\n总计: {len(logs)} probes, {lineup_available} with lineup ({lineup_available/len(logs)*100:.0f}%)")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Probe football-data.org for lineup availability")
    parser.add_argument("--match-id", type=str, help="Probe a specific match (football-data:id)")
    parser.add_argument("--probe-window", type=int, default=48,
                        help="Probe upcoming matches within N hours (default: 48)")
    parser.add_argument("--summary", action="store_true", help="Show probe history")
    args = parser.parse_args()

    if args.summary:
        await show_summary()
        return

    if args.match_id:
        print(f"🔍 Probing single match: {args.match_id}")
        result = await probe_match(args.match_id)
        async with AsyncSessionLocal() as db:
            await save_probe(db, result)
        print(json.dumps(result, indent=2, default=str))
        return

    results = await run_probes(args.probe_window)
    if results:
        lineup_count = sum(1 for r in results if r.get("has_lineup"))
        print(f"\n📊 Summary: {len(results)} probed, {lineup_count} with lineup data")


if __name__ == "__main__":
    asyncio.run(main())

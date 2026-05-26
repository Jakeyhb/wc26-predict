#!/usr/bin/env python3
"""
Sync finished match results from football-data.org for all configured leagues.

Features:
  --dry-run         Preview changes without writing to DB
  --league CODE     Sync only one league (PL/PD/BL1/SA/FL1/CL)
  --days N          Only sync matches from last N days (default: 30)

Idempotent: FINISHED + same score → skip; different score → CONFLICT warning.
Logs each run to ingest_runs table. Respects football-data.org rate limits.
"""

import argparse, asyncio, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def main():
    parser = argparse.ArgumentParser(description="Sync finished match results")
    parser.add_argument("--league", help="Competition code (PD/PL/BL1/SA/FL1/CL)")
    parser.add_argument("--days", type=int, default=30, help="Only sync matches from last N days")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing to DB")
    args = parser.parse_args()

    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select
    from app.services.football_data_service import FootballDataService, LEAGUE_COMPETITION_CODES
    from app.config import get_settings
    from app.models import Match, MatchResult, IngestRun
    from app.utils.datetime import utc_now

    settings = get_settings()
    engine = create_async_engine(settings.postgres_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    svc = FootballDataService()

    codes = [args.league] if args.league else list(LEAGUE_COMPETITION_CODES.keys())
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()

    # ── Counters ──────────────────────────────────────────────
    fetch_count = 0
    inserted_count = 0
    updated_count = 0
    skipped_count = 0
    conflict_count = 0
    failed_count = 0
    latest_date = None

    # ── IngestRun (create first, save ID for later update) ────
    async with async_session() as db:
        run = IngestRun(
            pipeline="sync_results",
            status="running",
            started_at=utc_now(),
            metadata_json={
                "league": args.league or "ALL",
                "days": args.days,
                "dry_run": args.dry_run,
            },
        )
        db.add(run)
        await db.commit()
        run_id = run.id

    # ── Sync each league ──────────────────────────────────────
    for i, code in enumerate(codes):
        async with async_session() as db:
            matches = await svc.fetch_competition_matches(code, season=2025, status="FINISHED")
            recent = [m for m in matches if m.get("utcDate", "") > cutoff]
            fetch_count += len(recent)
            print(f"[sync_results] {code}: {len(recent)} recent finished matches")

            for m in recent:
                try:
                    external_id = f"football-data:{m['id']}"

                    # Look up existing match
                    mr_result = await db.execute(
                        select(Match).where(Match.external_id == external_id)
                    )
                    existing = mr_result.scalar_one_or_none()

                    # ── Conflict / skip detection ──────────────
                    score = m.get("score", {}).get("fullTime", {})
                    api_home = int(score.get("home") or 0)
                    api_away = int(score.get("away") or 0)

                    if existing and existing.status == "finished":
                        rr = await db.execute(
                            select(MatchResult).where(
                                MatchResult.match_id == existing.id
                            )
                        )
                        mr = rr.scalar_one_or_none()

                        if mr:
                            if mr.home_goals == api_home and mr.away_goals == api_away:
                                skipped_count += 1
                                continue
                            else:
                                home_name = m.get("homeTeam", {}).get("name", "?")
                                away_name = m.get("awayTeam", {}).get("name", "?")
                                print(
                                    f"  ⚠ CONFLICT {home_name} vs {away_name}: "
                                    f"local {mr.home_goals}-{mr.away_goals}, "
                                    f"API {api_home}-{api_away}"
                                )
                                conflict_count += 1
                                continue

                    # ── Execute (or dry-run) ───────────────────
                    if not args.dry_run:
                        created = await svc._upsert_match_from_payload(m, db, code)
                        if created:
                            inserted_count += 1
                        else:
                            updated_count += 1
                    else:
                        home_name = m.get("homeTeam", {}).get("name", "?")
                        away_name = m.get("awayTeam", {}).get("name", "?")
                        if existing is None:
                            inserted_count += 1
                            print(f"  [DRY RUN] + {home_name} vs {away_name}  ({api_home}-{api_away})")
                        elif existing.status != "finished":
                            updated_count += 1
                            print(f"  [DRY RUN] ~ {home_name} vs {away_name}  ({api_home}-{api_away})")

                    # Track latest date
                    match_date = m.get("utcDate", "")
                    if not latest_date or match_date > latest_date:
                        latest_date = match_date

                except Exception as e:
                    failed_count += 1
                    print(f"  ERROR {m.get('id')}: {e}")

            if not args.dry_run:
                await db.commit()

        # ── 6-second interval between leagues (rate limit) ─────
        if i < len(codes) - 1:
            print(f"[sync_results] Sleeping 6s before next league…")
            await asyncio.sleep(6)

    # ── Update IngestRun ──────────────────────────────────────
    async with async_session() as db:
        result = await db.execute(select(IngestRun).where(IngestRun.id == run_id))
        ing_run = result.scalar_one()
        ing_run.status = "completed" if (failed_count == 0 and conflict_count == 0) else "partial_failed"
        ing_run.finished_at = utc_now()
        ing_run.items_seen = fetch_count
        ing_run.items_inserted = inserted_count
        ing_run.metadata_json = {
            **ing_run.metadata_json,
            "fetched": fetch_count,
            "inserted": inserted_count,
            "updated": updated_count,
            "skipped": skipped_count,
            "conflicts": conflict_count,
            "failed": failed_count,
            "latest_finished": latest_date or "N/A",
        }
        await db.commit()

    await engine.dispose()

    # ── Summary ───────────────────────────────────────────────
    print()
    print("=" * 55)
    print("Sync Results Summary")
    print(f"  league:           {args.league or 'ALL'}")
    print(f"  dry_run:          {args.dry_run}")
    print(f"  fetched:          {fetch_count}")
    print(f"  inserted:         {inserted_count}")
    print(f"  updated:          {updated_count}")
    print(f"  skipped:          {skipped_count}")
    print(f"  conflicts:        {conflict_count}")
    print(f"  failed:           {failed_count}")
    print(f"  latest_finished:  {latest_date or 'N/A'}")
    print(f"  status:           {'success' if failed_count == 0 else 'partial_failed'}")
    print("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())

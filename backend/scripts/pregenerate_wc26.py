"""Pregenerate WC2026 group-stage predictions.

Runs before the World Cup starts (June 11, 2026).  Results are stored
in prediction_snapshots so the content team can query them in < 0.1 s.

Expected runtime (vectorized DC + disk cache):
  - First match (cold start): ~30 s
  - Subsequent matches:       ~2 s (disk cache hit)
  - 72 group matches total:   ~3-5 min

Resumable - matches that already have a prediction_snapshot are skipped.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

from sqlalchemy import text
from app.database import AsyncSessionLocal


COMPETITION = "FIFA World Cup 2026"


async def get_wc_group_matches(db) -> list[dict]:
    result = await db.execute(text("""
        SELECT m.id, ht.name, at.name, m.match_date, m.is_neutral_venue, m.stage
        FROM matches m
        JOIN teams ht ON m.home_team_id = ht.id
        JOIN teams at ON m.away_team_id = at.id
        WHERE m.competition = :comp AND m.stage LIKE 'Group%'
        ORDER BY m.match_date
    """), {"comp": COMPETITION})
    return [
        {
            "id": str(row[0]).replace("-", ""),
            "home": row[1],
            "away": row[2],
            "date": str(row[3]),
            "neutral": bool(row[4]),
            "stage": row[5],
        }
        for row in result.fetchall()
    ]


async def already_predicted(db, match_id_hex: str) -> bool:
    result = await db.execute(text(
        "SELECT 1 FROM prediction_snapshots WHERE match_id = :mid LIMIT 1"
    ), {"mid": match_id_hex})
    return result.scalar() is not None


async def main():
    async with AsyncSessionLocal() as db:
        matches = await get_wc_group_matches(db)

    print(f"Found {len(matches)} WC26 group-stage matches ({COMPETITION})")

    from scripts.snapshot import run_snapshot
    from app.services.snapshot_store import save_prediction_snapshot

    success, skipped, failed = 0, 0, 0
    t_start = time.perf_counter()

    for i, m in enumerate(matches, 1):
        label = f"[{i:>3d}/{len(matches)}] {m['date'][:10]}  {m['home']} vs {m['away']} ({m['stage']})"
        print(f"\n{'='*70}")
        print(label)
        print(f"{'='*70}")

        # Skip if already predicted
        async with AsyncSessionLocal() as db:
            if await already_predicted(db, m["id"]):
                print(f"  Skip - already predicted")
                skipped += 1
                continue

        t0 = time.perf_counter()
        try:
            result = await run_snapshot(
                home_team=m["home"],
                away_team=m["away"],
                is_neutral=m["neutral"],
                competition=COMPETITION,
            )
            await save_prediction_snapshot(result, run_type="manual")
            dt = time.perf_counter() - t0
            print(f"  OK ({dt:.0f}s)")
            success += 1
        except Exception as exc:
            dt = time.perf_counter() - t0
            print(f"  FAIL ({dt:.0f}s): {exc}")
            failed += 1

    dt_total = time.perf_counter() - t_start
    print(f"\n{'='*70}")
    print(f"Done: {success} ok  {skipped} skip  {failed} fail")
    print(f"Total: {dt_total/60:.1f} min  Avg: {dt_total/len(matches):.0f}s/match")
    print(f"{'='*70}")


if __name__ == "__main__":
    import os
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    asyncio.run(main())

"""Daily operations hub — single entry point for Windows Task Scheduler.

Usage:
    python scripts/daily_ops.py --task health
    python scripts/daily_ops.py --task fetch-market
    python scripts/daily_ops.py --task postmatch
    python scripts/daily_ops.py --task backup
    python scripts/daily_ops.py --task pregenerate

Design: Each task is independent and idempotent. Failures are logged but
don't block other tasks. No Celery/RabbitMQ/Redis dependency.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ["POSTGRES_URL"] = "sqlite+aiosqlite:///./data/local_stage2.db"
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DATA_DIR = PROJECT_ROOT / "data"
BACKUP_DIR = DATA_DIR / "backups"


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


# ── Tasks ──────────────────────────────────────────────────

async def task_health():
    """Health check: DB connectivity, prediction counts, data freshness."""
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    log("Health check starting...")
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("SELECT 1"))
        log("  DB: OK")

        r = await db.execute(text("SELECT COUNT(*) FROM prediction_snapshots"))
        log(f"  Prediction snapshots: {r.scalar()}")

        r = await db.execute(text(
            "SELECT COUNT(*) FROM news_articles WHERE is_processed = 0"
        ))
        log(f"  Unprocessed articles: {r.scalar()}")

        r = await db.execute(text("SELECT COUNT(*) FROM news_signals"))
        log(f"  News signals: {r.scalar()}")

        r = await db.execute(text(
            "SELECT COUNT(*) FROM matches "
            "WHERE competition = 'FIFA World Cup 2026' "
            "AND match_date > datetime('now') "
            "AND match_date < datetime('now', '+1 days')"
        ))
        log(f"  Matches in next 24h: {r.scalar()}")
    log("Health check done.")


async def task_fetch_market():
    """Fetch market odds for upcoming WC26 matches."""
    log("Market fetch starting...")
    from app.services.market_calibrator import get_calibrator

    cal = get_calibrator(shadow_mode=True)
    available = await cal.is_available()
    log(f"  Market calibrator available: {available}")

    if available:
        # Fetch for next WC26 match
        from app.database import AsyncSessionLocal
        from sqlalchemy import text
        async with AsyncSessionLocal() as db:
            r = await db.execute(text(
                "SELECT ht.name, at.name FROM matches m "
                "JOIN teams ht ON m.home_team_id = ht.id "
                "JOIN teams at ON m.away_team_id = at.id "
                "WHERE m.competition = 'FIFA World Cup 2026' "
                "AND m.match_date > datetime('now') "
                "ORDER BY m.match_date LIMIT 1"
            ))
            row = r.fetchone()
            if row:
                home, away = row
                log(f"  Fetching odds: {home} vs {away}")
                try:
                    probs = await cal.fetch_market_probs(home, away, 1.5, competition="FIFA World Cup 2026")
                    if probs:
                        log(f"  Odds fetched: home={probs['home_prob']:.3f}")
                    else:
                        log("  No odds available for this match")
                except Exception as e:
                    log(f"  Fetch error: {e}")
            else:
                log("  No upcoming WC26 matches found")
    log("Market fetch done.")


async def task_postmatch():
    """Run post-match evaluation for recent matches."""
    log("Post-match evaluation starting...")
    script = SCRIPTS_DIR / "auto_postmatch.py"
    if script.exists():
        try:
            result = subprocess.run(
                [sys.executable, str(script)],
                cwd=str(PROJECT_ROOT),
                capture_output=True, text=True, timeout=300,
            )
            log(f"  Exit: {result.returncode}")
            if result.stdout:
                for line in result.stdout.strip().split("\n")[-5:]:
                    log(f"    {line}")
        except subprocess.TimeoutExpired:
            log("  TIMEOUT after 300s")
        except Exception as e:
            log(f"  Error: {e}")
    else:
        log(f"  Script not found: {script}")
    log("Post-match done.")


async def task_backup():
    """Backup database and export health report."""
    log("Backup starting...")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    db_path = DATA_DIR / "local_stage2.db"
    if db_path.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = BACKUP_DIR / f"local_stage2_{ts}.db"
        import shutil
        shutil.copy2(str(db_path), str(dst))
        size_mb = dst.stat().st_size / (1024 * 1024)
        log(f"  DB backed up: {dst.name} ({size_mb:.1f} MB)")

        # Clean old backups (keep last 7)
        backups = sorted(BACKUP_DIR.glob("*.db"), key=os.path.getmtime, reverse=True)
        for old in backups[7:]:
            old.unlink()
            log(f"  Removed old backup: {old.name}")
    else:
        log(f"  DB not found: {db_path}")

    # Export health snapshot
    health_file = BACKUP_DIR / f"health_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    await task_health()  # prints to stdout — we just rely on the log
    log(f"  Health check logged")

    log("Backup done.")


async def task_pregenerate():
    """Regenerate predictions for WC26 group matches that need updating."""
    log("Pregenerate starting...")
    script = SCRIPTS_DIR / "pregenerate_wc26.py"
    if script.exists():
        try:
            result = subprocess.run(
                [sys.executable, str(script)],
                cwd=str(PROJECT_ROOT),
                capture_output=True, text=True, timeout=600,
            )
            log(f"  Exit: {result.returncode}")
            for line in result.stdout.strip().split("\n")[-5:]:
                log(f"    {line}")
        except subprocess.TimeoutExpired:
            log("  TIMEOUT after 600s")
        except Exception as e:
            log(f"  Error: {e}")
    log("Pregenerate done.")


# ── Task registry ─────────────────────────────────────────

TASKS = {
    "health": task_health,
    "fetch-market": task_fetch_market,
    "postmatch": task_postmatch,
    "backup": task_backup,
    "pregenerate": task_pregenerate,
}


async def main():
    parser = argparse.ArgumentParser(description="Daily operations hub")
    parser.add_argument("--task", required=True, choices=list(TASKS.keys()),
                        help="Task to run")
    args = parser.parse_args()

    log(f"DailyOps: {args.task}")
    await TASKS[args.task]()
    log(f"DailyOps: {args.task} — DONE")


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""Daily post-match sweep for WC26.
Checks if ALL today's matches are finished + 180 minutes have passed since
the last kickoff. If conditions are met, runs auto_postmatch.py.
Otherwise exits silently (intended to be called every 10 minutes by Cron).

Usage:
    python daily_post_match.py [--date 2026-06-14] [--force] [--delay-min 180]
"""
from __future__ import annotations

import subprocess, sys, sqlite3
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BACKEND_DIR / "data" / "local_stage2.db"
PYTHON = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
POSTMATCH_SCRIPT = BACKEND_DIR / "scripts" / "auto_postmatch.py"
STATE_PATH = BACKEND_DIR / "data" / "daily_postmatch_state.json"

CST = timezone(timedelta(hours=8))


def _load_state():
    if STATE_PATH.exists():
        import json
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def _save_state(state: dict):
    import json
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def get_today_matches(conn, target_date: date):
    """Get all WC26 matches for a given date."""
    rows = conn.execute("""
        SELECT m.id, m.match_date, m.status,
               ht.name AS home, at.name AS away
        FROM matches m
        JOIN teams ht ON ht.id = m.home_team_id
        JOIN teams at ON at.id = m.away_team_id
        WHERE m.competition LIKE '%World Cup 2026%'
          AND date(m.match_date) = ?
        ORDER BY m.match_date
    """, (target_date.isoformat(),)).fetchall()
    return rows


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Daily post-match sweep checker")
    parser.add_argument("--date", help="Target date (YYYY-MM-DD), default=today")
    parser.add_argument("--force", action="store_true", help="Run even if conditions not met")
    parser.add_argument("--delay-min", type=int, default=180,
                       help="Minutes after last kickoff to wait (default: 180)")
    args = parser.parse_args()

    target_date = date.fromisoformat(args.date) if args.date else date.today()
    now = datetime.now(CST)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    matches = get_today_matches(conn, target_date)
    conn.close()

    key = target_date.isoformat()

    if not matches:
        # No matches that day. Mark done and exit silent.
        state = _load_state()
        state[key] = {"status": "no_matches", "checked_at": now.isoformat()}
        _save_state(state)
        return 0

    # Check 1: Are all matches finished?
    finished = [m for m in matches if m["status"] == "finished"]
    has_results = []
    for m in matches:
        conn2 = sqlite3.connect(str(DB_PATH))
        r = conn2.execute("SELECT 1 FROM match_results WHERE match_id = ?",
                          (m["id"].replace("-", ""),)).fetchone()
        conn2.close()
        has_results.append(r is not None)

    all_done = all(
        m["status"] == "finished" or has_results[i]
        for i, m in enumerate(matches)
    )

    if not all_done and not args.force:
        # Not all finished yet. Exit silent.
        return 0

    # Check 2: Has 180 min passed since last kickoff?
    last_kickoff = None
    for m in matches:
        kt = m["match_date"]
        if isinstance(kt, str):
            kt = datetime.fromisoformat(kt.replace("Z", "+00:00"))
        if kt.tzinfo is None:
            from datetime import timezone as tz
            kt = kt.replace(tzinfo=tz.utc)
        kt_cst = kt.astimezone(CST)
        if last_kickoff is None or kt_cst > last_kickoff:
            last_kickoff = kt_cst

    if last_kickoff:
        minutes_since = (now - last_kickoff).total_seconds() / 60
        if minutes_since < args.delay_min and not args.force:
            # Not enough time passed. Exit silent.
            return 0

    # Check 3: Already processed today?
    state = _load_state()
    today_state = state.get(key, {})
    if today_state.get("status") == "done" and not args.force:
        return 0

    # RUN POST-MATCH SWEEP
    cmd = [str(PYTHON), str(POSTMATCH_SCRIPT), "--days", "1"]
    proc = subprocess.run(
        cmd, cwd=str(BACKEND_DIR), text=True, encoding="utf-8",
        errors="replace", capture_output=True, timeout=300,
        env={**__import__("os").environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    )

    print(f"# WC26 每日赛后复盘 — {target_date.isoformat()}")
    print(f"  执行时间：{now.strftime('%Y-%m-%d %H:%M CST')}")
    print(f"  比赛场次：{len(matches)}/{len(finished)} 已完赛")
    print(f"  返回码：{proc.returncode}")
    print()
    print(proc.stdout[-8000:] if proc.stdout else "(no output)")
    if proc.stderr:
        print(f"\n```\n{proc.stderr[-2000:]}\n```")

    state[key] = {
        "status": "done" if proc.returncode == 0 else "failed",
        "ran_at": now.isoformat(),
        "returncode": proc.returncode,
        "matches_total": len(matches),
        "matches_finished": len(finished),
    }
    _save_state(state)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())

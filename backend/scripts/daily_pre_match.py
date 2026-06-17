#!/usr/bin/env python3
"""Daily batch pre-match prediction for WC26.
Runs at 12:00 CST daily — predicts ALL matches scheduled for TOMORROW.
Generates full prediction report for each match, then a daily digest.

Usage:
    python daily_pre_match.py [--date 2026-06-15] [--force]
"""
from __future__ import annotations

import subprocess, sys, sqlite3, re
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BACKEND_DIR / "data" / "local_stage2.db"
PYTHON = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
PREDICT_SCRIPT = BACKEND_DIR / "scripts" / "predict_wc26.py"
REPORT_DIR = BACKEND_DIR / "reports"

CST = timezone(timedelta(hours=8))


def _connect():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def find_tomorrow_matches(conn, target_date: str | None = None):
    """Find all WC26 matches for tomorrow (or given date)."""
    if target_date:
        d = date.fromisoformat(target_date)
    else:
        d = date.today() + timedelta(days=1)

    rows = conn.execute("""
        SELECT m.id, m.match_date, m.stage, m.venue,
               ht.name AS home, at.name AS away, m.status
        FROM matches m
        JOIN teams ht ON ht.id = m.home_team_id
        JOIN teams at ON at.id = m.away_team_id
        WHERE m.competition LIKE '%World Cup 2026%'
          AND date(m.match_date) = ?
        ORDER BY m.match_date
    """, (d.isoformat(),)).fetchall()
    return rows, d


def run_prediction(home: str, away: str) -> dict:
    """Run predict_wc26.py for one match. Returns {ok, stdout, stderr, report}."""
    cmd = [
        str(PYTHON), str(PREDICT_SCRIPT),
        "--home", home, "--away", away,
        "--competition", "FIFA World Cup 2026",
        "--neutral",
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=str(BACKEND_DIR), text=True, encoding="utf-8",
            errors="replace", capture_output=True, timeout=600,
            env={**__import__("os").environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "timeout (600s)", "report": None, "rc": 124}

    # Extract report path from stdout
    report = None
    for line in proc.stdout.splitlines():
        m = re.search(r"Report:\s*(.+?\.md)", line)
        if m:
            report = m.group(1).strip().strip('"')
            if not Path(report).is_absolute():
                report = str(BACKEND_DIR / report)

    return {
        "ok": proc.returncode == 0 and report is not None and Path(report).exists(),
        "stdout": proc.stdout, "stderr": proc.stderr,
        "report": report, "rc": proc.returncode,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Daily batch WC26 pre-match prediction")
    parser.add_argument("--date", help="Target date (YYYY-MM-DD), default=tomorrow")
    parser.add_argument("--force", action="store_true", help="Re-run even if prediction exists")
    args = parser.parse_args()

    conn = _connect()
    matches, target_date = find_tomorrow_matches(conn, args.date)
    conn.close()

    if not matches:
        print(f"# WC26 每日赛前预测 — {target_date.isoformat()}")
        print(f"\n该日无 WC26 比赛。")
        return 0

    now_cst = datetime.now(CST)
    print(f"# WC26 每日赛前预测 — {target_date.isoformat()}")
    print(f"  生成时间：{now_cst.strftime('%Y-%m-%d %H:%M CST')}")
    print(f"  比赛场次：{len(matches)} 场")
    print()

    results = []
    for i, m in enumerate(matches, 1):
        home, away = m["home"], m["away"]
        kickoff = m["match_date"]
        stage = m["stage"] or "-"
        venue = m["venue"] or "-"

        print(f"## [{i}/{len(matches)}] {home} vs {away}")
        print(f"  阶段：{stage}  |  开球：{kickoff}  |  场馆：{venue}")
        print()

        result = run_prediction(home, away)
        results.append({**m, **result})

        if result["ok"]:
            print(f"  ✅ 预测完成 → `{result['report']}`")
        else:
            print(f"  ❌ 预测失败 (rc={result['rc']})")
            if result["stderr"]:
                tail = "\n".join(result["stderr"].splitlines()[-5:])
                print(f"  ```\n{tail}\n```")
        print()

    # Summary
    ok_count = sum(1 for r in results if r["ok"])
    print("---")
    print(f"## 汇总：{ok_count}/{len(results)} 场成功")
    for r in results:
        status = "✅" if r["ok"] else "❌"
        print(f"- {status} {r['home']} vs {r['away']} → {r.get('report', 'FAILED')}")

    # Save digest to report dir
    digest = REPORT_DIR / f"daily_pre_{target_date.isoformat()}_{now_cst.strftime('%H%M')}.md"
    # Re-print to capture? Actually this is stdout. Let's also save.
    return 0 if ok_count == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

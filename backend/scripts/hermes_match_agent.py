#!/usr/bin/env python3
"""Hermes/Task-Scheduler match automation watcher for WC26 Predict.

This script is intentionally self-contained and safe to run every few minutes.
It scans the local SQLite schedule, runs due pre-match predictions, runs a
post-match learning sweep when finished results are available, and prints a
Markdown digest to stdout only when something happened.

Typical usage from backend/:
    python scripts/hermes_match_agent.py --mode both --pre-window-min 180

Hermes no-agent cron usage:
    hermes cron create "every 10m" --no-agent --script wc26_match_watchdog.py \
        --deliver telegram --name wc26-match-watchdog

The wrapper in ~/.hermes/scripts/wc26_match_watchdog.py should call this file
with absolute paths. This avoids relying on Hermes cron's working directory.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

try:  # Python 3.9+
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

if sys.platform == "win32":
    # Windows Task Scheduler often defaults to a non-UTF-8 console code page.
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB = BACKEND_DIR / "data" / "local_stage2.db"
DEFAULT_STATE = BACKEND_DIR / "data" / "hermes_agent_state.json"
DEFAULT_REPORT_DIR = BACKEND_DIR / "reports" / "hermes"
WC26_COMPETITION = "FIFA World Cup 2026"


@dataclass(frozen=True)
class MatchRow:
    id: str
    match_date: datetime
    competition: str
    stage: str | None
    venue: str | None
    status: str
    is_neutral: bool
    home: str
    away: str

    @property
    def label(self) -> str:
        return f"{self.home} vs {self.away}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_db_datetime(value: str, assume_tz: timezone = timezone.utc) -> datetime:
    raw = str(value).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        # SQLite datetime('now') style fallback: 2026-06-11 14:00:00
        dt = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=assume_tz)
    return dt.astimezone(timezone.utc)


def _display_time(dt: datetime, tz_name: str) -> str:
    if ZoneInfo is None:
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M %Z")


def _connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "actions": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        # Keep the broken file for forensics and start clean.
        broken = path.with_suffix(path.suffix + f".broken-{datetime.now().strftime('%Y%m%d%H%M%S')}")
        path.replace(broken)
        return {"version": 1, "actions": {}, "recovered_from": str(broken)}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _query_matches(conn: sqlite3.Connection) -> list[MatchRow]:
    rows = conn.execute(
        """
        SELECT m.id, m.match_date, m.competition, m.stage, m.venue, m.status,
               m.is_neutral_venue, ht.name AS home_name, at.name AS away_name
        FROM matches m
        JOIN teams ht ON ht.id = m.home_team_id
        JOIN teams at ON at.id = m.away_team_id
        WHERE m.competition = ?
        ORDER BY m.match_date ASC
        """,
        (WC26_COMPETITION,),
    ).fetchall()
    matches: list[MatchRow] = []
    for row in rows:
        matches.append(
            MatchRow(
                id=str(row["id"]),
                match_date=_parse_db_datetime(row["match_date"]),
                competition=str(row["competition"]),
                stage=row["stage"],
                venue=row["venue"],
                status=str(row["status"]),
                is_neutral=bool(row["is_neutral_venue"]),
                home=str(row["home_name"]),
                away=str(row["away_name"]),
            )
        )
    return matches


def _has_match_result(conn: sqlite3.Connection, match_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM match_results WHERE match_id = ? LIMIT 1",
        (match_id.replace("-", ""),),
    ).fetchone()
    return row is not None


def _prediction_exists(conn: sqlite3.Connection, match: MatchRow) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM prediction_snapshots
        WHERE match_id LIKE ?
           OR (home_team = ? AND away_team = ? AND competition = ?)
        LIMIT 1
        """,
        (f"{match.id.replace('-', '')}%", match.home, match.away, match.competition),
    ).fetchone()
    return row is not None


def _action_key(prefix: str, match_id: str) -> str:
    return f"{prefix}:{match_id.replace('-', '')}"


def _state_done(state: dict[str, Any], key: str) -> bool:
    return state.get("actions", {}).get(key, {}).get("status") == "done"


def _state_recent_attempt(state: dict[str, Any], key: str, retry_after_min: int, now: datetime) -> bool:
    item = state.get("actions", {}).get(key)
    if not item:
        return False
    ts = item.get("last_attempt_at") or item.get("done_at")
    if not ts:
        return False
    try:
        then = _parse_db_datetime(str(ts))
    except Exception:
        return False
    return now - then < timedelta(minutes=retry_after_min)


def _record_action(
    state: dict[str, Any],
    key: str,
    *,
    status: str,
    match: MatchRow | None,
    report_path: str | None = None,
    returncode: int | None = None,
    note: str | None = None,
) -> None:
    actions = state.setdefault("actions", {})
    now_iso = _utc_now().isoformat()
    payload: dict[str, Any] = {
        "status": status,
        "last_attempt_at": now_iso,
    }
    if status == "done":
        payload["done_at"] = now_iso
    if match is not None:
        payload.update(
            {
                "match_id": match.id,
                "home": match.home,
                "away": match.away,
                "kickoff_utc": match.match_date.isoformat(),
            }
        )
    if report_path:
        payload["report_path"] = report_path
    if returncode is not None:
        payload["returncode"] = returncode
    if note:
        payload["note"] = note
    actions[key] = {**actions.get(key, {}), **payload}


def _run_command(
    args: list[str],
    *,
    timeout: int,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    # App settings resolve this relative path against cwd=BACKEND_DIR.
    env.setdefault("POSTGRES_URL", "sqlite+aiosqlite:///./data/local_stage2.db")
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        args,
        cwd=str(BACKEND_DIR),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
    )


def _extract_report_path(stdout: str) -> str | None:
    matches = re.findall(r"Report:\s*(.+?\.md)", stdout)
    if not matches:
        return None
    path = matches[-1].strip().strip('"')
    p = Path(path)
    if not p.is_absolute():
        p = BACKEND_DIR / p
    return str(p)


def _read_report(path: str | None, max_chars: int) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n> 报告过长，已截断；请打开本地文件查看全文。"


def _write_digest(report_dir: Path, title: str, body: str) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", title).strip("_")[:90] or "wc26_digest"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = report_dir / f"{ts}_{safe}.md"
    path.write_text(body, encoding="utf-8")
    return path


def _send_with_hermes(target: str, subject: str, file_path: Path) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["hermes", "send", "--to", target, "--subject", subject, "--file", str(file_path), "--quiet"],
            cwd=str(BACKEND_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
        )
        return result.returncode, (result.stdout or result.stderr or "").strip()
    except FileNotFoundError:
        return 127, "hermes CLI not found in PATH"
    except subprocess.TimeoutExpired:
        return 124, "hermes send timed out"


def _due_pre_matches(
    matches: Iterable[MatchRow],
    *,
    now: datetime,
    pre_window_min: int,
    min_before_min: int,
) -> list[MatchRow]:
    due: list[MatchRow] = []
    for match in matches:
        if match.status.lower() not in {"scheduled", "timed"}:
            continue
        minutes_to_kickoff = (match.match_date - now).total_seconds() / 60
        if min_before_min <= minutes_to_kickoff <= pre_window_min:
            due.append(match)
    return due


def _post_candidates(
    conn: sqlite3.Connection,
    matches: Iterable[MatchRow],
    *,
    now: datetime,
    post_delay_min: int,
    lookback_hours: int,
) -> list[MatchRow]:
    earliest = now - timedelta(hours=lookback_hours)
    due: list[MatchRow] = []
    for match in matches:
        if match.match_date < earliest:
            continue
        if now - match.match_date < timedelta(minutes=post_delay_min):
            continue
        # Do not learn from scheduled rows unless a result record already exists.
        if match.status.lower() != "finished" and not _has_match_result(conn, match.id):
            continue
        if _has_match_result(conn, match.id):
            due.append(match)
    return due


def run_pre_match(
    conn: sqlite3.Connection,
    state: dict[str, Any],
    match: MatchRow,
    *,
    force: bool,
    include_existing_predictions: bool,
    timeout: int,
    report_chars: int,
    tz_name: str,
) -> tuple[str, str | None, int]:
    key = _action_key("pre", match.id)
    if not force and _state_done(state, key):
        return "", None, 0
    if not force and not include_existing_predictions and _prediction_exists(conn, match):
        _record_action(state, key, status="done", match=match, note="prediction snapshot already existed")
        return "", None, 0

    cmd = [
        sys.executable,
        str(BACKEND_DIR / "scripts" / "predict_wc26.py"),
        "--home",
        match.home,
        "--away",
        match.away,
        "--competition",
        match.competition,
    ]
    if match.is_neutral:
        cmd.append("--neutral")

    try:
        proc = _run_command(cmd, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _record_action(state, key, status="failed", match=match, returncode=124, note="prediction timeout")
        body = (
            f"# WC26 自动赛前预测失败：{match.label}\n\n"
            f"- 开球时间：{_display_time(match.match_date, tz_name)}\n"
            f"- 失败原因：预测脚本超过 {timeout} 秒未完成\n"
            f"- 命令：`{' '.join(cmd)}`\n"
        )
        return body, None, 124

    report_path = _extract_report_path(proc.stdout)
    ok = proc.returncode == 0 and report_path is not None
    _record_action(
        state,
        key,
        status="done" if ok else "failed",
        match=match,
        report_path=report_path,
        returncode=proc.returncode,
        note=None if ok else "prediction command failed or report path missing",
    )

    if ok:
        report_text = _read_report(report_path, report_chars)
        body = (
            f"# WC26 自动赛前预测：{match.label}\n\n"
            f"- 开球时间：{_display_time(match.match_date, tz_name)}\n"
            f"- 阶段：{match.stage or 'N/A'}\n"
            f"- 场馆：{match.venue or 'N/A'}\n"
            f"- 本地报告：`{report_path}`\n\n"
            f"---\n\n"
            f"{report_text}\n"
        )
        return body, report_path, 0

    stdout_tail = "\n".join(proc.stdout.splitlines()[-80:])
    stderr_tail = "\n".join(proc.stderr.splitlines()[-80:])
    body = (
        f"# WC26 自动赛前预测失败：{match.label}\n\n"
        f"- 开球时间：{_display_time(match.match_date, tz_name)}\n"
        f"- 返回码：{proc.returncode}\n\n"
        f"## stdout\n\n```text\n{stdout_tail}\n```\n\n"
        f"## stderr\n\n```text\n{stderr_tail}\n```\n"
    )
    return body, None, proc.returncode


def run_postmatch_sweep(
    state: dict[str, Any],
    matches: list[MatchRow],
    *,
    now: datetime,
    retry_after_min: int,
    timeout: int,
    days: int,
    tz_name: str,
) -> tuple[str, int]:
    sweep_key = "postmatch_sweep"
    if _state_recent_attempt(state, sweep_key, retry_after_min, now):
        return "", 0

    cmd = [sys.executable, str(BACKEND_DIR / "scripts" / "auto_postmatch.py"), "--days", str(days)]
    try:
        proc = _run_command(cmd, timeout=timeout)
    except subprocess.TimeoutExpired:
        state.setdefault("actions", {})[sweep_key] = {
            "status": "failed",
            "last_attempt_at": now.isoformat(),
            "note": "auto_postmatch timeout",
            "candidate_match_ids": [m.id for m in matches],
        }
        body = (
            "# WC26 自动赛后复盘失败\n\n"
            f"- 候选比赛数：{len(matches)}\n"
            f"- 失败原因：auto_postmatch 超过 {timeout} 秒未完成\n"
        )
        return body, 124

    stdout_tail = proc.stdout.strip()
    stderr_tail = proc.stderr.strip()
    # Mark the sweep attempt; auto_postmatch itself protects learning with verification gates.
    state.setdefault("actions", {})[sweep_key] = {
        "status": "done" if proc.returncode == 0 else "failed",
        "last_attempt_at": now.isoformat(),
        "returncode": proc.returncode,
        "candidate_match_ids": [m.id for m in matches],
    }

    match_lines = "\n".join(
        f"- {m.label} | {_display_time(m.match_date, tz_name)} | {m.status}" for m in matches[:20]
    )
    body = (
        "# WC26 自动赛后复盘扫描\n\n"
        f"- 候选比赛数：{len(matches)}\n"
        f"- 返回码：{proc.returncode}\n"
        f"- 说明：学习链路仍要求至少两个独立可信赛果来源；来源不足时会跳过学习，不会污染模型。\n\n"
        f"## 候选比赛\n\n{match_lines or '- N/A'}\n\n"
        f"## auto_postmatch 输出\n\n```text\n{stdout_tail[-8000:]}\n```\n"
    )
    if stderr_tail:
        body += f"\n## stderr\n\n```text\n{stderr_tail[-4000:]}\n```\n"
    return body, proc.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WC26 Hermes match automation watcher")
    parser.add_argument("--mode", choices=["pre", "post", "both"], default="both")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path")
    parser.add_argument("--state", default=str(DEFAULT_STATE), help="Idempotency state JSON path")
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR), help="Digest output directory")
    parser.add_argument("--pre-window-min", type=int, default=180, help="Run predictions when kickoff is within this many minutes")
    parser.add_argument("--min-before-min", type=int, default=0, help="Do not run prediction if kickoff is closer than this many minutes")
    parser.add_argument("--post-delay-min", type=int, default=150, help="Wait this many minutes after kickoff before post-match sweep")
    parser.add_argument("--lookback-hours", type=int, default=36, help="Look back this many hours for post-match candidates")
    parser.add_argument("--post-retry-min", type=int, default=180, help="Minimum minutes between postmatch sweep attempts")
    parser.add_argument("--post-days", type=int, default=3, help="auto_postmatch --days value")
    parser.add_argument("--timeout", type=int, default=900, help="Timeout per subprocess in seconds")
    parser.add_argument("--report-chars", type=int, default=14000, help="Max prediction report chars printed to stdout")
    parser.add_argument("--tz", default="Asia/Shanghai", help="Display timezone for reports")
    parser.add_argument("--force", action="store_true", help="Ignore idempotency state and run due actions again")
    parser.add_argument("--include-existing-predictions", action="store_true", help="Notify even when a prediction snapshot already exists")
    parser.add_argument("--send-to", default=None, help="Optional Hermes send target, e.g. telegram or discord:#ops")
    parser.add_argument("--verbose", action="store_true", help="Print a no-action heartbeat")
    args = parser.parse_args(argv)

    db_path = Path(args.db).resolve()
    state_path = Path(args.state).resolve()
    report_dir = Path(args.report_dir).resolve()
    state = _load_state(state_path)
    now = _utc_now()

    bodies: list[str] = []
    return_code = 0

    try:
        conn = _connect(db_path)
    except Exception as exc:
        body = f"# WC26 自动化扫描失败\n\n无法打开数据库：`{db_path}`\n\n```text\n{exc}\n```\n"
        print(body)
        return 2

    try:
        matches = _query_matches(conn)
        if args.mode in {"pre", "both"}:
            for match in _due_pre_matches(
                matches,
                now=now,
                pre_window_min=args.pre_window_min,
                min_before_min=args.min_before_min,
            ):
                body, _report, rc = run_pre_match(
                    conn,
                    state,
                    match,
                    force=args.force,
                    include_existing_predictions=args.include_existing_predictions,
                    timeout=args.timeout,
                    report_chars=args.report_chars,
                    tz_name=args.tz,
                )
                if body:
                    bodies.append(body)
                if rc != 0:
                    return_code = rc

        if args.mode in {"post", "both"}:
            candidates = _post_candidates(
                conn,
                matches,
                now=now,
                post_delay_min=args.post_delay_min,
                lookback_hours=args.lookback_hours,
            )
            if candidates:
                body, rc = run_postmatch_sweep(
                    state,
                    candidates,
                    now=now,
                    retry_after_min=args.post_retry_min,
                    timeout=args.timeout,
                    days=args.post_days,
                    tz_name=args.tz,
                )
                if body:
                    bodies.append(body)
                if rc != 0:
                    return_code = rc
    finally:
        conn.close()
        _save_state(state_path, state)

    if not bodies:
        if args.verbose:
            print(f"WC26 watcher: no due actions at {_display_time(now, args.tz)}")
        return 0

    digest_body = "\n\n---\n\n".join(bodies)
    digest_path = _write_digest(report_dir, "wc26_automation_digest", digest_body)
    # Make the local path visible even if the digest body is sent by Hermes cron.
    final_body = f"{digest_body}\n\n---\n\n本地自动化摘要：`{digest_path}`\n"

    if args.send_to:
        send_rc, send_msg = _send_with_hermes(args.send_to, "WC26 自动化报告", digest_path)
        final_body += f"\nHermes send：{'OK' if send_rc == 0 else 'FAILED'}"
        if send_msg:
            final_body += f"\n\n```text\n{send_msg}\n```\n"
        if send_rc != 0 and return_code == 0:
            return_code = send_rc

    print(final_body)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())

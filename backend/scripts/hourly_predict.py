#!/usr/bin/env python3
"""Hourly prediction runner for a single high-profile match.

Usage:
    python scripts/hourly_predict.py \\
        --home "Paris Saint-Germain FC" \\
        --away "Arsenal FC" \\
        --competition "Champions League" \\
        --train-leagues "Ligue 1" "Premier League" \\
        --neutral \\
        --extra-context "PSG 4-3-3 vs Arsenal 4-2-3-1..."

What it does:
    1. Runs snapshot.py with full prediction pipeline
    2. Captures prediction output to reports/ dir
    3. Calls POST /api/analysis/generate for AI analysis
    4. Prints summary: probs, xG, top scores, analysis excerpt

If the backend isn't running, starts it in the background first.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import urllib.request

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
REPORTS_DIR = BACKEND_DIR / "reports"

# ── Load env ────────────────────────────────────────────────
for env_file in [BACKEND_DIR / ".env", BACKEND_DIR / ".." / ".env.local"]:
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    if key.strip() and key.strip() not in os.environ:
                        os.environ[key.strip()] = val.strip().strip('"').strip("'")

LLM_KEY = os.environ.get("LLM_API_KEY", os.environ.get("LLM_API_KEY_ALT", ""))
API_BASE = "http://localhost:8000"


def ensure_backend():
    """Check if backend is running, start if not."""
    try:
        urllib.request.urlopen(f"{API_BASE}/api/health", timeout=3)
        print("✅ 后端运行中")
        return True
    except Exception:
        print("⚠️  后端未运行，正在启动...")
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
            cwd=str(BACKEND_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(10):
            time.sleep(3)
            try:
                urllib.request.urlopen(f"{API_BASE}/api/health", timeout=3)
                print("✅ 后端已启动")
                return True
            except Exception:
                pass
        print("❌ 后端启动失败")
        return False


def run_snapshot(home, away, competition, train_leagues, neutral):
    """Run snapshot.py and capture output."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    report_path = REPORTS_DIR / f"{timestamp}_{home.replace(' ', '_')}_vs_{away.replace(' ', '_')}.md"

    cmd = [sys.executable, str(SCRIPT_DIR / "snapshot.py"), "--home", home, "--away", away, "--competition", competition]
    if neutral:
        cmd.append("--neutral")
    if train_leagues:
        cmd.extend(["--competitions"] + train_leagues)

    print(f"\n{'='*60}")
    print(f"🔮 运行预测流水线 ({timestamp})...")
    print(f"{'='*60}\n")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND_DIR)
    # Ensure SQLite mode (not PostgreSQL)
    env.setdefault("POSTGRES_URL", "sqlite+aiosqlite:///./data/local_stage2.db")

    result = subprocess.run(cmd, cwd=str(BACKEND_DIR), env=env, capture_output=True, text=True, timeout=180)

    if result.returncode != 0:
        print(f"❌ 预测失败: {result.stderr[:500]}")
        return None

    # Save report
    output = result.stdout
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path.write_text(output, encoding="utf-8")
    print(f"📄 报告已保存: {report_path.name}")

    return output


def generate_analysis(match_id, extra_context=""):
    """Call analysis API and return result."""
    if not LLM_KEY:
        return "⚠️  LLM_API_KEY 未设置，跳过 AI 分析"

    print("\n🤖 生成 AI 深度分析...")

    payload = json.dumps({"match_id": match_id, "extra_context": extra_context})
    req = urllib.request.Request(
        f"{API_BASE}/api/analysis/generate",
        data=payload.encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode())
            return data.get("analysis", "")
    except Exception as e:
        return f"❌ AI 分析失败: {e}"


def extract_match_id(snapshot_output):
    """Extract match name from snapshot output for display."""
    for line in snapshot_output.split("\n"):
        if "快照已存入数据库" in line:
            return True
    return False


def print_summary(snapshot_output, analysis):
    """Print key predictions."""
    print(f"\n{'='*60}")
    print("📊 预测摘要")
    print(f"{'='*60}")

    # Extract probs
    for line in snapshot_output.split("\n"):
        if "模型预测" in line or "主胜" in line or "期望进球" in line or "Top 3" in line or "1:" in line or "0:" in line:
            if any(c in line for c in ["|", "1:", "0:", "期望进球", "模型预测"]):
                print(line)

    print(f"\n{'='*60}")
    if analysis and len(analysis) > 20:
        print("🤖 AI 分析报告:")
        print(f"{'='*60}")
        print(analysis[:600] + ("..." if len(analysis) > 600 else ""))
    print(f"\n{'='*60}")
    print(f"⏱  生成时间: {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Hourly prediction runner")
    parser.add_argument("--home", required=True)
    parser.add_argument("--away", required=True)
    parser.add_argument("--competition", required=True)
    parser.add_argument("--train-leagues", nargs="+", default=[])
    parser.add_argument("--neutral", action="store_true")
    parser.add_argument("--extra-context", default="")
    parser.add_argument("--match-id", default="")
    parser.add_argument("--skip-analysis", action="store_true")
    args = parser.parse_args()

    if not ensure_backend():
        sys.exit(1)

    # Step 1: Snapshot
    output = run_snapshot(args.home, args.away, args.competition, args.train_leagues, args.neutral)
    if not output:
        sys.exit(1)

    # Step 2: AI Analysis
    analysis = ""
    if not args.skip_analysis:
        analysis = generate_analysis(args.match_id or "", args.extra_context)

    # Step 3: Summary
    print_summary(output, analysis)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""smoke_dashboard.py — Minimal smoke test for the Dashboard.

Checks: streamlit installed, all page files exist, Dashboard starts and
serves a page containing "WC26 Predict".

Usage: python scripts/smoke_dashboard.py [--port 8501]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
DASHBOARD_DIR = BACKEND_DIR / "dashboard"
PAGES_DIR = DASHBOARD_DIR / "pages"

EXPECTED_PAGES = [
    "01_Overview.py", "02_Match_Prediction.py", "03_Match_Context.py",
    "04_WC26_Schedule.py", "05_Teams_Facts.py", "06_Database_Explorer.py",
    "07_Tournament_Simulator.py", "08_Creator_Mode.py",
]


def check_streamlit() -> bool:
    try:
        import streamlit  # noqa: F401
        return True
    except ImportError:
        return False


def check_files() -> list[str]:
    missing = []
    app_py = DASHBOARD_DIR / "app.py"
    if not app_py.exists():
        missing.append(str(app_py))
    for page in EXPECTED_PAGES:
        if not (PAGES_DIR / page).exists():
            missing.append(str(PAGES_DIR / page))
    return missing


def start_dashboard(port: int) -> subprocess.Popen | None:
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run",
             str(DASHBOARD_DIR / "app.py"),
             "--server.port", str(port),
             "--server.address", "localhost",
             "--server.headless", "true"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=str(BACKEND_DIR),
        )
        return proc
    except Exception as e:
        print(f"  FAIL: Could not start Streamlit: {e}")
        return None


def check_response(port: int, timeout: int = 30) -> bool:
    url = f"http://localhost:{port}"
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            resp = urllib.request.urlopen(url, timeout=5)
            body = resp.read().decode("utf-8", errors="replace")
            if "WC26 Predict" in body:
                return True
            last_error = "Response did not contain WC26 Predict"
        except Exception as exc:
            last_error = str(exc)
            time.sleep(1)
    print(f"  FAIL: Could not reach {url} within {timeout}s: {last_error}")
    return False


def main() -> int:
    p = argparse.ArgumentParser(description="Smoke test for WC26 Predict Dashboard")
    p.add_argument("--port", type=int, default=8501)
    args = p.parse_args()
    port = args.port
    failures = 0

    print("WC26 Predict Dashboard Smoke Test")
    print("=" * 50)

    print("\n[1/4] Checking streamlit...")
    if check_streamlit():
        print("  OK: streamlit installed")
    else:
        print("  FAIL: streamlit not installed")
        failures += 1

    print("\n[2/4] Checking dashboard files...")
    missing = check_files()
    if missing:
        for m in missing:
            print(f"  MISSING: {m}")
        failures += 1
    else:
        print(f"  OK: app.py + {len(EXPECTED_PAGES)} pages")

    print(f"\n[3/4] Starting dashboard on port {port}...")
    proc = start_dashboard(port)
    if proc is None:
        failures += 1
    else:
        print(f"[4/4] Checking http://localhost:{port} ...")
        ok = check_response(port, timeout=30)
        if ok:
            print("  OK: Dashboard served WC26 Predict")
        else:
            failures += 1
        print("\nShutting down...")
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        print("  Stopped.")

    print("\n" + "=" * 50)
    if failures == 0:
        print("SMOKE TEST PASSED")
        return 0
    print(f"SMOKE TEST FAILED ({failures} failures)")
    return 1


if __name__ == "__main__":
    sys.exit(main())

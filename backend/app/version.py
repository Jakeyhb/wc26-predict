"""version.py — Single source of truth for the project version.

All modules (CLI, Dashboard, README, reports, smoke tests) MUST read
from this file. Never hardcode a version string elsewhere.
"""

import subprocess
from pathlib import Path

VERSION = "3.5.3-paired-benchmark"
TAG = "v3.5.3-paired-benchmark"
BUILD_NAME = "V3.5.3 Paired Benchmark — 同样本配对回测门 + 非配对leaderboard隔离"


def get_git_commit() -> str:
    """Return the current git commit hash, or empty string if unavailable."""
    try:
        repo_root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""

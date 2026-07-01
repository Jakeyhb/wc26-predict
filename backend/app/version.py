"""version.py — Single source of truth for the project version.

All modules (CLI, Dashboard, README, reports, smoke tests) MUST read
from this file. Never hardcode a version string elsewhere.
"""

import subprocess
from pathlib import Path

VERSION = "4.5.0-beta"
TAG = "v4.5.0-beta"
BUILD_NAME = "V4.5.0 测试版 — A3 Stacking元学习器 + B1加权共形预测 + 7组件21维特征 + 半衰期学习(180d最优) + 全文档化魔数注册表"


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

"""dashboard_config.py — Streamlit Dashboard 中心配置"""

from __future__ import annotations

import sys
from pathlib import Path

# ── 路径 ──────────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DASHBOARD_DIR = BACKEND_DIR / "dashboard"
DB_PATH = BACKEND_DIR / "data" / "local_stage2.db"
ARTIFACTS_DIR = BACKEND_DIR / "artifacts"
TEAM_FACTS_PATH = BACKEND_DIR.parent / "data" / "team_tournament_status.json"

# ── 应用元数据 ────────────────────────────────────────────────────────────────
from app.version import VERSION, BUILD_NAME  # noqa: E402

APP_TITLE = "WC26 Predict"
SUB_TITLE = "本地工作台"

# ── 预测模式 ──────────────────────────────────────────────────────────────────
PREDICTION_MODES: dict[str, str] = {
    "baseline": "仅 Dixon-Coles",
    "standard": "DC + Enhancer + Elo",
    "full": "DC + Enhancer + Elo + Pi",
}
DEFAULT_MODE = "full"

# ── WC26 常量 ─────────────────────────────────────────────────────────────────
GROUPS = list("ABCDEFGHIJKL")
EXPECTED_MATCHES = 104
EXPECTED_GROUP_MATCHES = 72
EXPECTED_TEAMS = 48

# ── 数据库安全 ────────────────────────────────────────────────────────────────
STRICT_READONLY = True
MAX_QUERY_ROWS = 1000
SQL_TIMEOUT_SECONDS = 30

# ── 模拟器默认值 ──────────────────────────────────────────────────────────────
SIMULATION_RUNS_OPTIONS = [1_000, 10_000, 50_000]
DEFAULT_SIMULATION_RUNS = 10_000

# ── 上下文事件类型 ────────────────────────────────────────────────────────────
CONTEXT_EVENT_TYPES = [
    "伤病",
    "停赛",
    "首发阵容",
    "天气",
    "旅途",
    "市场共识",
    "主帅发言",
]

# ── 页面配置 ──────────────────────────────────────────────────────────────────
PAGE_CONFIG = {
    "page_title": f"{APP_TITLE} {SUB_TITLE}",
    "page_icon": ":soccer:",
    "layout": "wide",
    "initial_sidebar_state": "expanded",
}

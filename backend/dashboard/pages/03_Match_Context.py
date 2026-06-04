"""03_Match_Context.py — 比赛上下文事件页面"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import streamlit as st

from dashboard.db import db
from dashboard.dashboard_config import CONTEXT_EVENT_TYPES

st.title("比赛上下文")
st.caption("查看和添加动态比赛上下文事件（伤病、首发、天气等）")

# ── 筛选控件 ──────────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    all_teams = ["（全部）"] + db.get_teams()
    filter_team = st.selectbox("按球队筛选", all_teams, key="ctx_team")
with col2:
    all_types = ["（全部）"] + CONTEXT_EVENT_TYPES
    filter_type = st.selectbox("按事件类型筛选", all_types, key="ctx_type")

# ── 加载事件 ──────────────────────────────────────────────────────────────────
team_param = None if filter_team == "（全部）" else filter_team
events = db.get_manual_events(team=team_param)

if filter_type != "（全部）" and events:
    events = [e for e in events if e.get("event_type", "").lower() == filter_type.lower()]

# ── 显示事件 ──────────────────────────────────────────────────────────────────
type_map = {
    "injury": "伤病", "suspension": "停赛", "lineup": "首发阵容",
    "weather": "天气", "travel": "旅途", "market_consensus": "市场共识",
    "coach_quote": "主帅发言",
}
status_map = {"active": "生效中", "expired": "已过期", "pending": "待审核"}

if events:
    st.caption(f"共 {len(events)} 条事件")

    for event in events[:50]:
        event_type = event.get("event_type", "未知")
        type_label = type_map.get(event_type, event_type)
        team_name = event.get("team_name", "?")
        player = event.get("player_name", "")
        severity = event.get("severity", "")
        status = event.get("status", "pending")
        status_label = status_map.get(status, status)
        affects_model = event.get("affects_model", False)
        source = event.get("source_url", "")
        note = event.get("note", event.get("description", ""))
        created = str(event.get("created_at", ""))[:16]

        status_color = {"active": "green", "expired": "gray", "pending": "orange"}.get(status, "gray")

        title = f":{status_color}[{status_label}] {type_label.upper()} — {team_name}"
        if player:
            title += f" — {player}"
        if severity:
            title += f" [{severity}]"

        with st.expander(title, expanded=(status == "active")):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.caption(f"球队: {team_name}")
                st.caption(f"类型: {type_label}")
                st.caption(f"状态: {status_label}")
            with c2:
                st.caption(f"严重程度: {severity or '无'}")
                st.caption(f"影响模型: {'是' if affects_model else '否'}")
                st.caption(f"创建时间: {created}")
            with c3:
                if source:
                    st.caption(f"来源: {source[:80]}...")
            if note:
                st.text(note)
else:
    st.info("暂无上下文事件。使用下方表单添加。")

# ── 添加事件表单 ──────────────────────────────────────────────────────────────
st.divider()
st.subheader("添加上下文事件")

with st.form("add_context_event", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
        new_team = st.selectbox("球队", db.get_teams(), key="ctx_new_team")
        new_type = st.selectbox("事件类型", CONTEXT_EVENT_TYPES, key="ctx_new_type")
        new_player = st.text_input("球员名称（选填）", key="ctx_new_player")
    with col2:
        new_severity = st.selectbox("严重程度", ["低", "中", "高", "严重"], key="ctx_new_severity")
        new_status = st.selectbox("状态", ["待审核", "生效中", "已过期"], key="ctx_new_status")
        new_confidence = st.slider("置信度", 0.0, 1.0, 0.5, 0.1, key="ctx_new_conf")

    new_source = st.text_input("来源链接", key="ctx_new_source")
    new_note = st.text_area("备注 / 描述", key="ctx_new_note")
    new_affects = st.checkbox("影响模型（仅确认数据可勾选）", value=False, key="ctx_new_affects")

    submitted = st.form_submit_button("添加事件")
    if submitted:
        if not new_note.strip():
            st.warning("请填写备注/描述")
        else:
            st.info(
                "事件已准备就绪。生产环境中会调用 add_manual_event.py 写入数据库。\n\n"
                f"球队: {new_team} | 类型: {new_type} | 严重程度: {new_severity} | 状态: {new_status}"
            )
            st.caption("注意: Dashboard 中禁用写入操作。请使用 CLI 脚本写入数据库。")

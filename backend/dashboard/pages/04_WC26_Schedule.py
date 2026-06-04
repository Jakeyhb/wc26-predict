"""04_WC26_Schedule.py — WC26 赛程浏览页面"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import streamlit as st
import pandas as pd

from dashboard.db import db
from dashboard.dashboard_config import GROUPS, EXPECTED_MATCHES

st.title("WC26 赛程")
st.caption(f"2026 年 FIFA 世界杯 — 共 {EXPECTED_MATCHES} 场比赛，12 个小组")

# ── 筛选控件 ──────────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    selected_groups = st.multiselect("按小组筛选", GROUPS, default=[], key="sched_groups")
with col2:
    view_mode = st.radio("视图", ["赛程表", "小组概览"], horizontal=True, key="sched_view")

# ── 加载数据 ──────────────────────────────────────────────────────────────────
schedule = db.get_wc26_schedule()
groups_data = db.get_wc26_groups()

if not schedule:
    st.warning("未找到 WC26 赛程数据。请先运行 seed_wc26_schedule.py。")
    st.stop()

df_schedule = pd.DataFrame(schedule)
df_groups = pd.DataFrame(groups_data) if groups_data else pd.DataFrame()

if selected_groups:
    if "group_name" in df_schedule.columns:
        df_schedule = df_schedule[df_schedule["group_name"].isin(selected_groups)]

# ── 视图: 赛程表 ──────────────────────────────────────────────────────────────
if view_mode == "赛程表":
    total = len(df_schedule)
    group_stage = len(df_schedule[df_schedule.get("stage", "") == "Group Stage"]) if "stage" in df_schedule.columns else 0
    knockout = total - group_stage

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("总场次", total)
    with c2:
        st.metric("小组赛", group_stage)
    with c3:
        st.metric("淘汰赛", knockout)

    display_cols = [
        c for c in ["match_number", "group_name", "home_team", "away_team",
                     "stage", "match_date", "venue", "city", "status"]
        if c in df_schedule.columns
    ]
    label_map = {
        "match_number": "场次", "group_name": "小组", "home_team": "主队",
        "away_team": "客队", "stage": "阶段", "match_date": "日期",
        "venue": "场馆", "city": "城市", "status": "状态",
    }
    st.dataframe(
        df_schedule[display_cols].rename(columns=label_map),
        use_container_width=True,
        hide_index=True,
        height=600,
    )

# ── 视图: 小组概览 ────────────────────────────────────────────────────────────
else:
    if df_groups.empty:
        st.warning("未找到小组数据。")
    else:
        for group_name in GROUPS:
            group_teams = df_groups[df_groups["group_name"] == group_name]
            if group_teams.empty:
                continue
            with st.expander(f"小组 {group_name}", expanded=(len(GROUPS) <= 4)):
                tc = [c for c in ["slot", "team_name", "team_code", "fifa_rank"] if c in group_teams.columns]
                tl = {"slot": "槽位", "team_name": "球队", "team_code": "代码", "fifa_rank": "FIFA排名"}
                st.dataframe(
                    group_teams[tc].rename(columns=tl),
                    use_container_width=True, hide_index=True,
                )
                group_matches = df_schedule[df_schedule["group_name"] == group_name]
                if not group_matches.empty:
                    st.caption("小组赛程:")
                    mc = [c for c in ["match_number", "home_team", "away_team", "match_date", "venue"] if c in group_matches.columns]
                    ml = {"match_number": "场次", "home_team": "主队", "away_team": "客队", "match_date": "日期", "venue": "场馆"}
                    st.dataframe(group_matches[mc].rename(columns=ml), use_container_width=True, hide_index=True)

st.divider()
st.caption("数据来源: FIFA 官方 — fifa.com + inside.fifa.com")

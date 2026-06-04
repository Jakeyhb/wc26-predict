"""05_Teams_Facts.py — 球队事实库页面"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import streamlit as st
import pandas as pd

from dashboard.dashboard_config import GROUPS, EXPECTED_TEAMS, TEAM_FACTS_PATH

st.title("球队事实库")
st.caption(f"{EXPECTED_TEAMS} 支已晋级球队的硬事实数据")

# ── 加载数据 ──────────────────────────────────────────────────────────────────
try:
    facts_data = json.loads(TEAM_FACTS_PATH.read_text("utf-8"))
    teams_dict = facts_data.get("teams", {})
    forbidden_q = facts_data.get("FORBIDDEN_PHRASES_IF_QUALIFIED", [])
    forbidden_e = facts_data.get("FORBIDDEN_PHRASES_IF_ELIMINATED", [])

    teams_list = []
    for name, info in teams_dict.items():
        teams_list.append({
            "球队": info.get("team_name", name),
            "身份": info.get("status", "未知"),
            "小组": info.get("group_name", "?"),
            "晋级路径": info.get("qualification_path", ""),
            "下一场正式比赛": info.get("next_official_match", ""),
            "小组对手": ", ".join(info.get("group_opponents", [])),
            "置信度": info.get("confidence", ""),
        })
except FileNotFoundError:
    st.error(f"球队事实文件未找到: {TEAM_FACTS_PATH}")
    st.stop()
except Exception as e:
    st.error(f"无法加载球队事实: {e}")
    st.stop()

df_teams = pd.DataFrame(teams_list)

# ── 摘要卡片 ──────────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("总球队数", len(teams_list))
with col2:
    qualified = len(df_teams[df_teams["身份"] == "qualified"])
    st.metric("已晋级", f"{qualified}/{EXPECTED_TEAMS}")
with col3:
    st.metric("小组数", len(df_teams["小组"].unique()) if not df_teams.empty else 0)
with col4:
    st.metric("禁用短语 (晋级)", len(forbidden_q))

# ── 筛选 ──────────────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    search = st.text_input("搜索球队", key="facts_search")
with col2:
    filter_group = st.selectbox("按小组筛选", ["（全部）"] + GROUPS, key="facts_group")

display_df = df_teams.copy()
if search:
    display_df = display_df[display_df["球队"].str.contains(search, case=False)]
if filter_group != "（全部）":
    display_df = display_df[display_df["小组"] == filter_group]

# ── 显示 ──────────────────────────────────────────────────────────────────────
st.subheader(f"球队列表 ({len(display_df)})")

if display_df.empty:
    st.info("没有符合当前筛选条件的球队。")
else:
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=600,
    )

# ── 禁用短语参考 ──────────────────────────────────────────────────────────────
with st.expander("禁用短语参考"):
    st.markdown("**对已晋级球队，禁止说:**")
    for phrase in forbidden_q[:10]:
        st.caption(f"- {phrase}")
    if len(forbidden_q) > 10:
        st.caption(f"... 还有 {len(forbidden_q) - 10} 条")

    st.markdown("**对已淘汰球队，禁止说:**")
    for phrase in forbidden_e[:5]:
        st.caption(f"- {phrase}")

st.divider()
st.caption(f"数据来源: {facts_data.get('source', 'FIFA')} | 版本: {facts_data.get('version', '?')}")

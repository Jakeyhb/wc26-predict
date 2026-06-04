"""02_Match_Prediction.py — 单场预测页面"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import streamlit as st

from dashboard.dashboard_config import PREDICTION_MODES, DEFAULT_MODE
from dashboard.db import db
from dashboard.components.probability_charts import (
    render_probability_gauge,
    render_scoreline_bars,
    render_xg_comparison,
    render_model_breakdown,
)
from dashboard.components.fusion_graph_view import render_fusion_graph
from dashboard.components.run_quality_panel import render_run_quality, render_timings
from app.services.prediction_core import run_artifact_pipeline


st.title("单场预测")
st.caption("运行 4 模型 artifact 推理预测（0 LLM token）")

# ── 输入表单 ──────────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns([2, 2, 1])

with col1:
    teams = db.get_teams()
    home_team = st.selectbox(
        "主队",
        teams,
        index=teams.index("France") if "France" in teams else 0,
        key="pred_home",
    )

with col2:
    away_team = st.selectbox(
        "客队",
        teams,
        index=teams.index("Ivory Coast") if "Ivory Coast" in teams else 1,
        key="pred_away",
    )

with col3:
    is_neutral = st.checkbox("中立场地", value=True, key="pred_neutral")

col1b, col2b = st.columns([3, 1])
with col1b:
    competition = st.text_input("赛事名称", value="International Friendly", key="pred_competition")
with col2b:
    mode = st.selectbox(
        "预测模式",
        list(PREDICTION_MODES.keys()),
        format_func=lambda m: PREDICTION_MODES[m],
        index=list(PREDICTION_MODES.keys()).index(DEFAULT_MODE),
        key="pred_mode",
    )

# ── 校验 ──────────────────────────────────────────────────────────────────────
can_predict = home_team != away_team
if not can_predict:
    st.warning("请选择不同的主队和客队")

# ── 运行预测 ──────────────────────────────────────────────────────────────────
if st.button("开始预测", type="primary", disabled=not can_predict):
    with st.spinner("正在运行预测管线..."):
        try:
            result, quality, timer = run_artifact_pipeline(
                home_team=home_team,
                away_team=away_team,
                competition=competition,
                is_neutral=is_neutral,
                mode=mode,
            )
            st.session_state["last_prediction"] = {
                "result": result,
                "quality": quality,
                "timings": timer.to_dict(),
                "total_seconds": round(timer.total(), 3),
            }
        except Exception as e:
            st.error(f"预测失败: {e}")
            st.stop()

    # ── 阶段标签 ──────────────────────────────────────────────────────────────
    st.divider()
    st.markdown("### :large_blue_circle: 基础模型预测")
    st.caption("首发阵容: 未获取 | 天气: 未查询 | 市场数据: 未查询")

    # ── 结果布局 ──────────────────────────────────────────────────────────────
    left, right = st.columns([3, 2])

    with left:
        st.subheader("胜平负概率")
        render_probability_gauge(
            result["home_win_prob"], result["draw_prob"], result["away_win_prob"],
            home_team, away_team,
        )

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric(f"{home_team} 胜", f"{result['home_win_prob'] * 100:.1f}%")
        with c2:
            st.metric("平局", f"{result['draw_prob'] * 100:.1f}%")
        with c3:
            st.metric(f"{away_team} 胜", f"{result['away_win_prob'] * 100:.1f}%")

        st.subheader("预期进球 (xG)")
        render_xg_comparison(result["home_xg"], result["away_xg"], home_team, away_team)

        st.subheader("最可能比分")
        render_scoreline_bars(result.get("top_scores", []))

        st.subheader("各模型独立预测")
        fg_data = result.get("fusion_graph", {})
        steps = fg_data.get("steps", [])
        if steps:
            component_probs = {}
            name_map = {
                "dixon_coles": "Dixon-Coles",
                "enhancer": "XGBoost 增强器",
                "elo": "Elo 评级",
                "pi_rating": "Pi 评级",
                "weibull": "Weibull",
            }
            for step in steps:
                before = step.get("before", {})
                for comp_name, probs in before.items():
                    if comp_name not in component_probs and len(probs) == 3:
                        display = name_map.get(comp_name, comp_name)
                        component_probs[display] = {"home": probs[0], "draw": probs[1], "away": probs[2]}
            if component_probs:
                render_model_breakdown(component_probs)

    with right:
        st.subheader("管线状态")
        render_run_quality(quality)

        st.subheader("性能耗时")
        render_timings(timer.to_dict(), timer.total())

        st.subheader("融合诊断")
        render_fusion_graph(fg_data)

        st.subheader("已启用组件")
        st.json(result.get("components_used", []))

    st.divider()
    st.caption("免责声明: 仅供内部研究。不构成投注建议。此为未接入首发/伤病/天气数据的基础模型预测。")

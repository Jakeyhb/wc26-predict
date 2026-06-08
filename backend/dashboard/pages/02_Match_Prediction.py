"""02_Match_Prediction.py — 单场预测页面 (V2.6 Enhanced)"""

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


st.title("单场预测")
st.caption("4 模型融合预测 + 实时市场赔率 + 天气 + AI 分析")

# ── 输入表单 ──────────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns([2, 2, 1])

with col1:
    teams = db.get_teams()
    home_team = st.selectbox(
        "主队",
        teams,
        index=teams.index("Spain") if "Spain" in teams else 0,
        key="pred_home",
    )

with col2:
    away_team = st.selectbox(
        "客队",
        teams,
        index=teams.index("Iraq") if "Iraq" in teams else 1,
        key="pred_away",
    )

with col3:
    is_neutral = st.checkbox("中立场地", value=True, key="pred_neutral")

col1b, col2b, col3b = st.columns([2, 1, 1])
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
with col3b:
    enhanced_mode = st.checkbox("增强模式", value=True, key="pred_enhanced",
                                help="启用市场赔率融合 + 天气 + AI 分析")

# ── 校验 ──────────────────────────────────────────────────────────────────────
can_predict = home_team != away_team
if not can_predict:
    st.warning("请选择不同的主队和客队")

# ── Enhanced mode ─────────────────────────────────────────────────────────────

def _run_enhanced(home_team, away_team, competition, is_neutral, mode):
    """Run enhanced prediction with market, weather, and LLM."""

    from app.services.prediction_enhanced import (
        run_enhanced_prediction,
        enhanced_result_to_dict,
    )

    # ── Phase 1: Base artifact prediction ──
    with st.status("正在运行增强预测...", expanded=True) as status:
        st.write("🔬 运行基础模型 (Dixon-Coles + Enhancer + Elo + Pi)...")
        try:
            enhanced = run_enhanced_prediction(
                home_team=home_team,
                away_team=away_team,
                competition=competition,
                is_neutral=is_neutral,
                mode=mode,
                enable_market=True,
                enable_weather=True,
                enable_llm=True,
            )
        except Exception as e:
            st.error(f"预测失败: {e}")
            st.stop()

        # Store for Creator Mode
        session_dict = enhanced_result_to_dict(enhanced)
        st.session_state["last_prediction"] = session_dict
        # Also store the enhanced object for direct access
        st.session_state["last_enhanced"] = enhanced

        status.update(label=f"预测完成 — {enhanced.total_seconds:.1f}s", state="complete")

    # ── Results layout ──────────────────────────────────────────────────────
    result = enhanced.base_result

    st.divider()
    st.markdown("### ⚽ 预测结果")

    # Status tags
    tag_cols = st.columns(4)
    with tag_cols[0]:
        delta = ""
        if enhanced.market_divergence_triggered:
            st.warning(f"⚠️ 市场分歧 {enhanced.market_divergence*100:.1f}pp")
        elif enhanced.market_probs:
            st.success("✅ 市场数据已接入")
    with tag_cols[1]:
        if enhanced.weather and enhanced.weather.get("forecast_available"):
            st.info(f"🌤 {enhanced.weather.get('weather_description', '?')} {enhanced.weather.get('temperature_c', '?')}°C")
    with tag_cols[2]:
        if enhanced.is_ai_analyzed:
            st.success("🤖 AI 分析已生成")
    with tag_cols[3]:
        st.caption(f"⏱ {enhanced.total_seconds:.1f}s")

    left, right = st.columns([3, 2])

    with left:
        # ── Final probabilities (after market blend) ──
        st.subheader("最终概率" + (" (含市场融合)" if enhanced.market_blended else ""))
        render_probability_gauge(
            enhanced.final_home_prob,
            enhanced.final_draw_prob,
            enhanced.final_away_prob,
            home_team,
            away_team,
        )

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric(f"{home_team} 胜", f"{enhanced.final_home_prob * 100:.1f}%")
        with c2:
            st.metric("平局", f"{enhanced.final_draw_prob * 100:.1f}%")
        with c3:
            st.metric(f"{away_team} 胜", f"{enhanced.final_away_prob * 100:.1f}%")

        # ── Market comparison ──
        if enhanced.market_probs:
            st.subheader("市场赔率对比")
            mc1, mc2, mc3 = st.columns(3)
            mp = enhanced.market_probs
            with mc1:
                delta_h = (enhanced.final_home_prob - mp["home_prob"]) * 100
                st.metric(
                    f"{home_team} (市场)",
                    f"{mp['home_prob']*100:.1f}%",
                    delta=f"{delta_h:+.1f}pp vs 模型",
                )
            with mc2:
                delta_d = (enhanced.final_draw_prob - mp["draw_prob"]) * 100
                st.metric(
                    "平局 (市场)",
                    f"{mp['draw_prob']*100:.1f}%",
                    delta=f"{delta_d:+.1f}pp vs 模型",
                )
            with mc3:
                delta_a = (enhanced.final_away_prob - mp["away_prob"]) * 100
                st.metric(
                    f"{away_team} (市场)",
                    f"{mp['away_prob']*100:.1f}%",
                    delta=f"{delta_a:+.1f}pp vs 模型",
                )
            st.caption(f"数据来源: {mp.get('provider', 'unknown')}")

        # ── xG ──
        st.subheader("预期进球 (xG)")
        render_xg_comparison(result["home_xg"], result["away_xg"], home_team, away_team)

        # ── Top scores ──
        st.subheader("最可能比分")
        render_scoreline_bars(result.get("top_scores", []))

        # ── Model breakdown ──
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

        # ── Weather detail ──
        if enhanced.weather and enhanced.weather.get("forecast_available"):
            st.subheader("天气信息")
            w = enhanced.weather
            wc1, wc2, wc3, wc4 = st.columns(4)
            with wc1:
                st.metric("天气", w.get("weather_description", "?"))
            with wc2:
                st.metric("温度", f"{w.get('temperature_c', '?')}°C")
            with wc3:
                st.metric("风速", f"{w.get('wind_speed_kmh', '?')} km/h")
            with wc4:
                st.metric("湿度", f"{w.get('humidity_percent', '?')}%")
            if enhanced.weather_impact_tags:
                st.info(f"天气影响: {' | '.join(enhanced.weather_impact_tags)}")

    with right:
        st.subheader("管线状态")
        if enhanced.base_quality:
            render_run_quality(enhanced.base_quality)

        st.subheader("性能耗时")
        if enhanced.timings:
            render_timings(enhanced.timings.to_dict(), enhanced.timings.total())

        st.subheader("融合诊断")
        render_fusion_graph(fg_data)

        st.subheader("风险标签")
        if enhanced.risk_tags:
            for tag in enhanced.risk_tags:
                st.warning(tag)
        else:
            st.success("无特殊风险标签")

        st.subheader("已启用组件")
        all_components = list(enhanced.components_used)
        if enhanced.market_probs:
            all_components.append("market_odds")
        if enhanced.weather and enhanced.weather.get("forecast_available"):
            all_components.append("weather")
        if enhanced.is_ai_analyzed:
            all_components.append("llm_analysis")
        st.json(all_components)

    # ── AI Analysis ──────────────────────────────────────────────────────────
    if enhanced.is_ai_analyzed:
        st.divider()
        st.markdown("### 🤖 AI 赛前分析 (DeepSeek V4 Pro)")

        tab1, tab2, tab3 = st.tabs(["赛前分析", "视频脚本", "社交媒体文案"])

        with tab1:
            if enhanced.llm_analysis:
                st.markdown(enhanced.llm_analysis)
            else:
                st.info("AI 分析未生成")

        with tab2:
            if enhanced.llm_video_script:
                st.markdown(enhanced.llm_video_script)
            else:
                st.info("视频脚本未生成")

        with tab3:
            if enhanced.llm_social_copy:
                st.markdown(enhanced.llm_social_copy)
            else:
                st.info("社交媒体文案未生成")

    elif enhanced.llm_error:
        st.warning(f"AI 分析生成失败: {enhanced.llm_error}")


# ── Artifact-only mode (legacy behavior) ─────────────────────────────────────

def _run_artifact_only(home_team, away_team, competition, is_neutral, mode):
    """Run pure artifact prediction (original behavior)."""
    from app.services.prediction_core import run_artifact_pipeline

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

    st.divider()
    st.markdown("### :large_blue_circle: 基础模型预测")
    st.caption("首发阵容: 未获取 | 天气: 未查询 | 市场数据: 未查询")

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


# ── 运行预测 (placed after function definitions to avoid NameError) ──────────
if st.button("开始预测", type="primary", disabled=not can_predict):
    if enhanced_mode:
        _run_enhanced(home_team, away_team, competition, is_neutral, mode)
    else:
        _run_artifact_only(home_team, away_team, competition, is_neutral, mode)

    st.divider()
    st.caption("免责声明: 本内容仅用于足球研究和内容创作，不构成投注建议，也不保证比赛结果。")

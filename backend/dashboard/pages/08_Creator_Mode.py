"""08_Creator_Mode.py — 创作者模式 — 录屏和内容制作优化"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import streamlit as st

from dashboard.components.creator_cards import (
    render_creator_card,
    render_creator_conclusion,
    render_social_copy,
    render_video_script,
    render_wechat_copy,
)

st.title("创作者模式")
st.caption("为录屏展示和社交媒体内容制作优化的大屏视图")

# ── 检查是否有最近一次预测 ────────────────────────────────────────────────────
last_pred = st.session_state.get("last_prediction")

if last_pred is None:
    st.info("暂无预测数据。请先前往 **单场预测** 页面运行一次预测，然后回到此处。")
    st.divider()
    if st.button("加载演示数据", key="creator_demo"):
        st.session_state["last_prediction"] = {
            "result": {
                "home_team": "法国",
                "away_team": "科特迪瓦",
                "competition": "国际友谊赛",
                "is_neutral": True,
                "home_win_prob": 0.366,
                "draw_prob": 0.242,
                "away_win_prob": 0.392,
                "home_xg": 1.07,
                "away_xg": 0.71,
                "top_scores": [
                    {"score": "1:0", "prob": 0.175},
                    {"score": "0:0", "prob": 0.174},
                    {"score": "1:1", "prob": 0.134},
                ],
                "components_used": ["dixon_coles", "tabular_enhancer", "elo", "pi_rating"],
            },
            "quality": None,
            "timings": {},
            "total_seconds": 2.16,
        }
        st.rerun()

if last_pred is None:
    st.stop()

result = last_pred["result"]

home = result["home_team"]
away = result["away_team"]
comp = result["competition"]
h_prob = result["home_win_prob"] * 100
d_prob = result["draw_prob"] * 100
a_prob = result["away_win_prob"] * 100
home_xg = result["home_xg"]
away_xg = result["away_xg"]

# ── 大屏模式 ──────────────────────────────────────────────────────────────────
st.markdown("### 今日分析场次")
st.markdown(f"## :soccer: {home} vs {away}")
st.caption(f"{comp} | 中立场地 | 基础模型预测")
st.divider()

# 概率卡片
col1, col2, col3 = st.columns(3)
with col1:
    render_creator_card(f"{home} 胜", f"{h_prob:.1f}%", accent_color="#2E86AB")
with col2:
    render_creator_card("平局", f"{d_prob:.1f}%", accent_color="#A23B72")
with col3:
    render_creator_card(f"{away} 胜", f"{a_prob:.1f}%", accent_color="#F18F01")

st.divider()

# xG 对比
st.subheader("预期进球")
cx1, cx2 = st.columns(2)
with cx1:
    render_creator_card(f"{home} xG", f"{home_xg:.2f}", accent_color="#2E86AB")
with cx2:
    render_creator_card(f"{away} xG", f"{away_xg:.2f}", accent_color="#F18F01")

# 最可能比分
st.subheader("最可能比分")
scores = result.get("top_scores", [])
if scores:
    cols = st.columns(min(len(scores[:3]), 4))
    for i, s in enumerate(scores[:3]):
        with cols[i]:
            render_creator_card(s["score"], f"{s['prob'] * 100:.1f}%", accent_color="#00BFFF" if i == 0 else "#888888")

st.divider()

# 一句话结论
if h_prob > a_prob:
    conclusion = (
        f"WC26 Predict 四模型融合预测显示，{home} 略占优势，"
        f"胜率 {h_prob:.1f}%。但这是基础模型预测——首发阵容、伤病、天气等动态数据尚未接入。"
        f"赛后我将用实际比分进行复盘。"
    )
else:
    conclusion = (
        f"WC26 Predict 四模型融合预测显示，在这场中立场地比赛中，{away} 略占优势，"
        f"胜率 {a_prob:.1f}%。但这是基础模型预测——首发阵容、伤病、天气等动态数据尚未接入。"
        f"赛后我将用实际比分进行复盘。"
    )

render_creator_conclusion(conclusion)

st.divider()

# ── 内容工具 ──────────────────────────────────────────────────────────────────
st.subheader("内容工具")

tab1, tab2 = st.tabs(["视频口播脚本", "社交媒体文案"])

with tab1:
    st.markdown("#### 视频口播脚本")
    script = render_video_script(home, away, result)
    render_social_copy(script)

with tab2:
    st.markdown("#### 小红书 / 公众号文案")
    wechat = render_wechat_copy(home, away, result)
    render_social_copy(wechat)

# ── 技术详情（折叠）───────────────────────────────────────────────────────────
with st.expander("技术详情（参考用）"):
    st.json({
        "模型": "4 模型融合 (DC + Enhancer + Elo + Pi)",
        "耗时": f"{last_pred.get('total_seconds', '?')}秒",
        "组件": result.get("components_used", []),
        "预测阶段": "基础模型预测",
        "首发阵容": "未获取",
        "天气": "未查询",
        "市场数据": "未查询",
    })

st.divider()
st.caption("免责声明: 仅供内部研究。不构成投注建议。此为未接入动态上下文数据的基础模型预测。")

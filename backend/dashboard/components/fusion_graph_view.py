"""fusion_graph_view.py — 融合图可视化组件（中文版）"""

from __future__ import annotations

import streamlit as st


def render_effective_weights(weights: dict[str, float]) -> None:
    if not weights:
        st.caption("无权重数据")
        return
    rows = [
        {"模型": "Dixon-Coles", "有效权重": f"{weights.get('dc_effective', 0) * 100:.1f}%"},
        {"模型": "XGBoost 增强器", "有效权重": f"{weights.get('enhancer_effective', 0) * 100:.1f}%"},
        {"模型": "Elo 评级", "有效权重": f"{weights.get('elo_effective', 0) * 100:.1f}%"},
        {"模型": "Pi 评级", "有效权重": f"{weights.get('pi_effective', 0) * 100:.1f}%"},
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_blend_params(bp: dict[str, float]) -> None:
    if not bp:
        return
    st.caption(
        f"混合参数: DC={bp.get('dc_weight', 0):.3f}  "
        f"Elo={bp.get('elo_weight', 0):.3f}  "
        f"Pi={bp.get('pi_weight', 0):.3f}"
    )


def render_model_disagreement(disagreement: dict) -> None:
    max_diff = disagreement.get("max_home_diff", 0)
    if max_diff > 0.20:
        color, label = "#FF4444", "高"
    elif max_diff > 0.10:
        color, label = "#FFA500", "中"
    elif max_diff > 0.05:
        color, label = "#FFD700", "低"
    else:
        color, label = "#00C853", "一致"

    st.markdown(f"**模型分歧:** :{color}[{max_diff:.4f}] ({label})")


def render_fusion_steps(steps: list[dict]) -> None:
    if not steps:
        st.caption("无融合步骤记录")
        return

    name_map = {
        "dixon_coles": "Dixon-Coles",
        "enhancer": "XGBoost 增强器",
        "elo": "Elo 评级",
        "pi_rating": "Pi 评级",
        "weibull": "Weibull",
        "dc+enhancer": "DC+增强器",
        "dc+enhancer+elo": "DC+增强器+Elo",
        "dc+enhancer+elo+pi": "DC+增强器+Elo+Pi",
    }

    for i, step in enumerate(steps):
        name = step.get("name", f"第 {i + 1} 步")
        display_name = name_map.get(name, name)
        formula = step.get("formula", "")
        after = step.get("after", [0, 0, 0])

        with st.expander(f"第 {i + 1} 步: {display_name} | {formula}", expanded=(i < 2)):
            cols = st.columns(3)
            cols[0].metric("主胜", f"{after[0]:.4f}", f"{after[0] * 100:.1f}%")
            cols[1].metric("平局", f"{after[1]:.4f}", f"{after[1] * 100:.1f}%")
            cols[2].metric("客胜", f"{after[2]:.4f}", f"{after[2] * 100:.1f}%")

            before = step.get("before", {})
            if before:
                st.caption("输入:")
                for comp_name, probs in before.items():
                    display = name_map.get(comp_name, comp_name)
                    st.text(f"  {display}: 主={probs[0]:.4f} 平={probs[1]:.4f} 客={probs[2]:.4f}")


def render_fusion_graph(fg_dict: dict) -> None:
    if not fg_dict:
        st.caption("无融合数据")
        return

    bp = fg_dict.get("blend_params", {})
    ew = fg_dict.get("effective_weights", {})
    md = fg_dict.get("model_disagreement", {})
    steps = fg_dict.get("steps", [])

    render_blend_params(bp)
    st.subheader("有效权重")
    render_effective_weights(ew)
    render_model_disagreement(md)
    st.subheader("融合步骤")
    render_fusion_steps(steps)

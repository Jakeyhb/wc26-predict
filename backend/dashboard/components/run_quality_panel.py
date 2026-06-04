"""run_quality_panel.py — 管线运行质量可视化（中文版）"""

from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go

from app.services.run_quality import RunQuality


def render_run_quality(quality: RunQuality) -> None:
    status = quality.pipeline_status
    color_map = {"full": "green", "degraded": "orange", "failed": "red"}
    label_map = {"full": "完整", "degraded": "降级", "failed": "失败"}
    color = color_map.get(status, "gray")
    label = label_map.get(status, status)
    st.markdown(f"**管线状态:** :{color}[{label.upper()}]")

    if quality.warnings:
        with st.expander("警告信息", expanded=True):
            for w in quality.warnings:
                st.warning(w)

    if quality.model_components:
        icon_map = {
            "loaded_from_artifact": ":white_check_mark:",
            "used": ":white_check_mark:",
            "skipped": ":heavy_minus_sign:",
            "failed": ":x:",
            "unavailable": ":heavy_minus_sign:",
        }
        name_map = {
            "dixon_coles": "Dixon-Coles",
            "tabular_enhancer": "XGBoost 增强器",
            "weibull": "Weibull（可选）",
            "elo": "Elo 评级",
            "pi_rating": "Pi 评级",
            "signal_adjuster": "信号调整器",
            "market_shadow": "市场影子",
        }
        status_map = {
            "loaded_from_artifact": "已加载",
            "used": "已使用",
            "skipped": "已跳过",
            "failed": "失败",
            "unavailable": "不可用",
        }
        with st.expander("组件状态"):
            for comp, comp_status in quality.model_components.items():
                icon = icon_map.get(comp_status, ":grey_question:")
                display = name_map.get(comp, comp)
                slabel = status_map.get(comp_status, comp_status)
                st.text(f"  {icon} {display}: {slabel}")


def render_timings(timings: dict[str, float], total: float) -> None:
    if not timings:
        st.caption("无耗时数据")
        return

    name_map = {
        "load_registry": "加载注册表",
        "load_df": "加载数据",
        "load_dc": "加载 DC",
        "load_enhancer": "加载增强器",
        "load_elo": "加载 Elo",
        "load_pi": "加载 Pi",
        "dc_predict": "DC 预测",
        "enhancer_predict": "增强器预测",
        "elo_predict": "Elo 预测",
        "pi_predict": "Pi 预测",
        "fusion": "融合计算",
        "render_report": "渲染报告",
    }

    filtered = [(k, v) for k, v in timings.items() if v > 0.0005]
    filtered.sort(key=lambda x: x[1], reverse=True)
    names = [name_map.get(f[0], f[0]) for f in filtered]
    values = [f[1] for f in filtered]

    fig = go.Figure(go.Bar(
        x=values, y=names, orientation="h",
        marker_color="#2E86AB",
        text=[f"{v:.3f}s" for v in values],
        textposition="outside",
    ))
    fig.update_layout(
        xaxis=dict(title="秒", showgrid=True),
        yaxis=dict(title=""),
        margin=dict(l=10, r=60, t=10, b=10),
        height=max(120, len(names) * 28),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.caption(f"总计: {total:.3f} 秒")

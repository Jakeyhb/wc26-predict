"""probability_charts.py — 概率图表组件（中文版）"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st


def render_probability_gauge(
    home: float, draw: float, away: float,
    home_team: str, away_team: str,
) -> None:
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name=f"{home_team} 胜",
        x=[home * 100], y=["概率"], orientation="h",
        marker_color="#2E86AB",
        text=f"{home * 100:.1f}%", textposition="inside", insidetextanchor="middle",
    ))
    fig.add_trace(go.Bar(
        name="平局",
        x=[draw * 100], y=["概率"], orientation="h",
        marker_color="#A23B72",
        text=f"{draw * 100:.1f}%", textposition="inside", insidetextanchor="middle",
    ))
    fig.add_trace(go.Bar(
        name=f"{away_team} 胜",
        x=[away * 100], y=["概率"], orientation="h",
        marker_color="#F18F01",
        text=f"{away * 100:.1f}%", textposition="inside", insidetextanchor="middle",
    ))
    fig.update_layout(
        barmode="stack",
        xaxis=dict(title="", range=[0, 100], showticklabels=False, showgrid=False),
        yaxis=dict(showticklabels=False, showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        margin=dict(l=10, r=10, t=30, b=10), height=100,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_scoreline_bars(top_scores: list[dict], max_items: int = 5) -> None:
    if not top_scores:
        st.caption("无比分数据")
        return
    scores = top_scores[:max_items]
    labels = [s["score"] for s in scores]
    values = [s["prob"] * 100 for s in scores]

    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h", marker_color="#2E86AB",
        text=[f"{v:.1f}%" for v in values], textposition="outside",
    ))
    fig.update_layout(
        xaxis=dict(title="概率 (%)", range=[0, max(values) * 1.3], showgrid=True),
        yaxis=dict(title=""),
        margin=dict(l=10, r=60, t=10, b=10), height=200,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_xg_comparison(home_xg: float, away_xg: float, home_team: str, away_team: str) -> None:
    max_xg = max(home_xg, away_xg, 1.0) * 1.3
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name=home_team, x=["预期进球"], y=[home_xg],
        marker_color="#2E86AB", text=f"{home_xg:.2f}", textposition="outside",
    ))
    fig.add_trace(go.Bar(
        name=away_team, x=["预期进球"], y=[away_xg],
        marker_color="#F18F01", text=f"{away_xg:.2f}", textposition="outside",
    ))
    fig.update_layout(
        yaxis=dict(title="预期进球 (xG)", range=[0, max_xg], showgrid=True),
        xaxis=dict(title=""),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=10, r=10, t=30, b=10), height=250,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_model_breakdown(component_probs: dict[str, dict[str, float]]) -> None:
    if not component_probs:
        st.caption("无各模型数据")
        return
    models = list(component_probs.keys())
    home_vals = [component_probs[m].get("home", 0) * 100 for m in models]
    draw_vals = [component_probs[m].get("draw", 0) * 100 for m in models]
    away_vals = [component_probs[m].get("away", 0) * 100 for m in models]

    fig = go.Figure()
    fig.add_trace(go.Bar(name="主胜", x=models, y=home_vals, marker_color="#2E86AB"))
    fig.add_trace(go.Bar(name="平局", x=models, y=draw_vals, marker_color="#A23B72"))
    fig.add_trace(go.Bar(name="客胜", x=models, y=away_vals, marker_color="#F18F01"))
    fig.update_layout(
        barmode="group",
        yaxis=dict(title="概率 (%)", range=[0, 100], showgrid=True),
        legend=dict(orientation="h"),
        margin=dict(l=10, r=10, t=10, b=10), height=300,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

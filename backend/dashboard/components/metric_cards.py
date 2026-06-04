"""metric_cards.py — 可复用指标卡片组件（中文版）"""

from __future__ import annotations

import streamlit as st


def render_metric_card(
    label: str, value: str, delta: str | None = None, help_text: str | None = None,
    *, border: bool = True,
) -> None:
    st.metric(label=label, value=value, delta=delta, help=help_text, border=border)


def render_metric_row(
    metrics: list[tuple[str, str, str | None]], *, columns: int = 4,
) -> None:
    cols = st.columns(columns)
    for i, (label, value, delta) in enumerate(metrics):
        with cols[i % columns]:
            render_metric_card(label, value, delta)


def render_status_badge(status: str) -> None:
    color_map = {"full": "green", "degraded": "orange", "failed": "red"}
    label_map = {"full": "完整", "degraded": "降级", "failed": "失败"}
    color = color_map.get(status, "gray")
    label = label_map.get(status, status.upper())
    st.markdown(f"**:{color}[{label}]**")

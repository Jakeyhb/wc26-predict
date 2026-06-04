"""database_table.py — 数据表查看器组件（中文版）"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st


def render_table_preview(
    data: list[dict[str, Any]] | pd.DataFrame,
    *,
    max_rows: int = 100,
) -> None:
    if isinstance(data, list):
        if not data:
            st.caption("无数据")
            return
        df = pd.DataFrame(data)
    else:
        df = data

    display_df = df.head(max_rows)
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    if len(df) > max_rows:
        st.caption(f"显示前 {max_rows} 行，共 {len(df)} 行")


def render_table_info(columns: list[dict[str, Any]]) -> None:
    if not columns:
        st.caption("无列元数据")
        return
    rows = []
    for c in columns:
        rows.append({
            "列名": c["name"],
            "类型": c["type"],
            "可空": "是" if c.get("notnull") is not True else "否",
            "主键": ":heavy_check_mark:" if c.get("pk") else "",
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_csv_download(df: pd.DataFrame, filename: str = "导出.csv") -> None:
    csv = df.to_csv(index=False)
    st.download_button(label="下载 CSV", data=csv, file_name=filename, mime="text/csv")

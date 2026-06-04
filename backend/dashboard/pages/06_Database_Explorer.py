"""06_Database_Explorer.py — 只读数据库浏览器页面"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import streamlit as st

from dashboard.db import db, _validate_read_only
from dashboard.dashboard_config import MAX_QUERY_ROWS
from dashboard.components.database_table import (
    render_table_preview,
    render_table_info,
    render_csv_download,
)

st.title("数据库浏览器")
st.caption("只读 SQLite 浏览器 — 仅允许 SELECT 查询")

# ── 表选择器 ──────────────────────────────────────────────────────────────────
tables = db.get_tables()

if not tables:
    st.warning("数据库中未找到任何表。")
    st.stop()

selected_table = st.selectbox("选择数据表", tables, key="dbex_table")

# ── 表信息 ────────────────────────────────────────────────────────────────────
if selected_table:
    col1, col2 = st.columns(2)
    with col1:
        row_count = db.get_row_count(selected_table)
        st.metric("行数", f"{row_count:,}")
    with col2:
        col_info = db.get_table_info(selected_table)
        st.metric("列数", len(col_info))

    with st.expander("列元数据"):
        render_table_info(col_info)

    st.subheader(f"预览: {selected_table}")
    rows = db.query(f"SELECT * FROM '{selected_table}' LIMIT 100")
    render_table_preview(rows, max_rows=MAX_QUERY_ROWS)

    if rows:
        import pandas as pd
        df = pd.DataFrame(rows)
        render_csv_download(df, f"{selected_table}.csv")

# ── SQL 查询输入 ──────────────────────────────────────────────────────────────
st.divider()
st.subheader("自定义 SQL 查询（仅 SELECT）")

default_sql = f"SELECT * FROM '{selected_table}' LIMIT 20" if selected_table else "SELECT 1"
sql = st.text_area(
    "SQL 查询",
    value=default_sql,
    height=100,
    key="dbex_sql",
    placeholder="SELECT * FROM 表名 LIMIT 100",
)

col1, col2 = st.columns([1, 4])
with col1:
    run_query = st.button("执行查询", type="primary", key="dbex_run")

with col2:
    if run_query and sql.strip():
        try:
            _validate_read_only(sql)
        except ValueError as e:
            st.error(str(e))
            st.stop()

if run_query and sql.strip():
    try:
        import pandas as pd
        result = db.query(sql.strip(), as_df=True)
        st.caption(f"查询返回 {len(result)} 行")
        if isinstance(result, pd.DataFrame):
            st.dataframe(result, use_container_width=True)
            render_csv_download(result, "查询结果.csv")
        else:
            render_table_preview(result, max_rows=MAX_QUERY_ROWS)
    except Exception as e:
        st.error(f"查询失败: {e}")

st.divider()
st.caption(f"数据库路径: {db.db_path} | 模式: 只读 | 最大行数: {MAX_QUERY_ROWS}")

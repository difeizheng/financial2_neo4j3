"""Data Browser page — search and browse all cells."""
import streamlit as st
import pandas as pd

from graph.neo4j_client import Neo4jClient
from graph.queries import (
    search_cells,
    get_cell_upstream,
    get_cell_downstream,
    list_sheets,
    get_sheet_sections,
)
from pages import navigate_to

PAGE_SIZE = 50


def render(client: Neo4jClient) -> None:
    st.title("🔍 数据浏览器")

    if not client.verify_connectivity():
        st.error("无法连接 Neo4j，请检查配置。")
        return

    # --- Search + filters ---
    search_query = st.text_input("搜索（标签/描述/公式/值）", placeholder="例：建设期、SUM、89")

    sheets = list_sheets(client)
    sheet_ids = ["（全部）"] + [s["id"] for s in sheets]

    f1, f2, f3, f4, f5 = st.columns([2, 2, 2, 2, 1])
    with f1:
        sel_sheet = st.selectbox("Sheet", sheet_ids, key="browser_sheet")
    with f2:
        sec_options = ["（全部）"]
        if sel_sheet != "（全部）":
            secs = get_sheet_sections(client, sel_sheet)
            sec_options += [s["name"] for s in secs]
        sel_sec_name = st.selectbox("Section", sec_options, key="browser_sec")
    with f3:
        categories = [
            "（全部）", "input_parameter", "financial_statement", "time_series",
            "depreciation", "cost", "revenue", "cashflow", "balance_sheet", "general",
        ]
        sel_cat = st.selectbox("业务分类", categories, key="browser_cat")
    with f4:
        vtypes = ["（全部）", "number", "string", "date", "boolean", "null"]
        sel_vtype = st.selectbox("值类型", vtypes, key="browser_vtype")
    with f5:
        is_head_opt = st.selectbox("表头", ["全部", "是", "否"], key="browser_head")

    # Build filters
    filters: dict = {}
    if sel_sheet != "（全部）":
        filters["sheet"] = sel_sheet
    if sel_sec_name != "（全部）" and sel_sheet != "（全部）":
        secs = get_sheet_sections(client, sel_sheet)
        sec_map = {s["name"]: s["id"] for s in secs}
        if sel_sec_name in sec_map:
            filters["section_id"] = sec_map[sel_sec_name]
    if sel_cat != "（全部）":
        filters["category"] = sel_cat
    if sel_vtype != "（全部）":
        filters["value_type"] = sel_vtype
    if is_head_opt == "是":
        filters["is_head"] = True
    elif is_head_opt == "否":
        filters["is_head"] = False

    # Pagination state
    if "browser_page" not in st.session_state:
        st.session_state["browser_page"] = 0

    # Reset page on filter change
    filter_key = str((search_query, str(filters)))
    if st.session_state.get("_browser_last_filter") != filter_key:
        st.session_state["browser_page"] = 0
        st.session_state["_browser_last_filter"] = filter_key

    page = st.session_state["browser_page"]

    with st.spinner("查询中…"):
        rows, total = search_cells(client, search_query, filters, page, PAGE_SIZE)

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    st.caption(f"共 {total:,} 条结果，第 {page + 1}/{total_pages} 页")

    # Pagination controls
    p1, p2, p3 = st.columns([1, 6, 1])
    with p1:
        if st.button("◀ 上一页", disabled=page == 0):
            st.session_state["browser_page"] -= 1
            st.rerun()
    with p3:
        if st.button("下一页 ▶", disabled=page >= total_pages - 1):
            st.session_state["browser_page"] += 1
            st.rerun()

    if not rows:
        st.info("无匹配结果。")
        return

    # --- Results table ---
    df = pd.DataFrame(rows)
    display_cols = ["id", "sheet", "section_name", "label", "value", "unit", "formula", "value_type", "description"]
    display_cols = [c for c in display_cols if c in df.columns]
    col_labels = {
        "id": "Cell ID", "sheet": "Sheet", "section_name": "Section",
        "label": "标签", "value": "值", "unit": "单位",
        "formula": "公式", "value_type": "类型", "description": "描述",
    }
    df_display = df[display_cols].rename(columns=col_labels)
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    # --- Row actions ---
    st.subheader("操作")
    sel_cell_id = st.selectbox(
        "选择 Cell 进行操作",
        options=[r["id"] for r in rows],
        format_func=lambda x: f"{x}  ({next((r['label'] for r in rows if r['id'] == x), '') or '无标签'})",
        key="browser_sel_cell",
    )

    act1, act2, act3 = st.columns(3)
    with act1:
        if st.button("🕸️ 在图谱中查看", key="browser_to_graph"):
            st.session_state["active_cell"] = sel_cell_id
            navigate_to("graph_view")
    with act2:
        if st.button("🔄 模拟变更", key="browser_to_sim"):
            st.session_state["active_cell"] = sel_cell_id
            navigate_to("simulation")

    # --- Cell detail panel ---
    with st.expander(f"📋 Cell 详情：{sel_cell_id}", expanded=False):
        cell_row = next((r for r in rows if r["id"] == sel_cell_id), None)
        if cell_row:
            d1, d2 = st.columns(2)
            with d1:
                st.write(f"**标签**: {cell_row.get('label') or '—'}")
                st.write(f"**Sheet**: {cell_row.get('sheet') or '—'}")
                st.write(f"**Section**: {cell_row.get('section_name') or '—'}")
                st.write(f"**业务分类**: {cell_row.get('section_category') or '—'}")
                st.write(f"**值**: `{cell_row.get('value')}`")
                st.write(f"**单位**: {cell_row.get('unit') or '—'}")
            with d2:
                st.write(f"**公式**: `{cell_row.get('formula') or '无'}`")
                st.write(f"**值类型**: {cell_row.get('value_type') or '—'}")
                st.write(f"**行分类**: {cell_row.get('row_category') or '—'}")
                st.write(f"**列分类**: {cell_row.get('col_category') or '—'}")
                st.write(f"**描述**: {cell_row.get('description') or '—'}")

            dep_col1, dep_col2 = st.columns(2)
            with dep_col1:
                st.write("**上游依赖（此 Cell 依赖的）**")
                upstream = get_cell_upstream(client, sel_cell_id)
                if upstream:
                    st.dataframe(pd.DataFrame(upstream), use_container_width=True, hide_index=True)
                else:
                    st.caption("无上游依赖")
            with dep_col2:
                st.write("**下游依赖（依赖此 Cell 的）**")
                downstream = get_cell_downstream(client, sel_cell_id)
                if downstream:
                    st.dataframe(pd.DataFrame(downstream), use_container_width=True, hide_index=True)
                else:
                    st.caption("无下游依赖")

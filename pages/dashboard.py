"""Workbook Dashboard page."""
import streamlit as st

from graph.neo4j_client import Neo4jClient
from graph.queries import (
    get_workbook_stats,
    get_section_category_distribution,
    get_sheet_dependency_matrix,
    get_top_depended_cells,
    list_sheets,
)
from pages import navigate_to

_CATEGORY_LABELS = {
    "input_parameter": "参数输入",
    "financial_statement": "财务报表",
    "time_series": "时间序列",
    "depreciation": "折旧摊销",
    "cost": "成本",
    "revenue": "收入",
    "cashflow": "现金流",
    "balance_sheet": "资产负债",
    "general": "通用",
}


def render(client: Neo4jClient) -> None:
    st.title("📊 工作簿仪表盘")

    wb_id = st.session_state.get("active_workbook")
    if not wb_id:
        st.info("请先在侧边栏选择工作簿，或从任务列表跳转。")
        return

    if not client.verify_connectivity():
        st.error("无法连接 Neo4j，请检查配置。")
        return

    st.caption(f"Workbook: `{wb_id}`")

    # --- Stats ---
    with st.spinner("加载统计数据…"):
        stats = get_workbook_stats(client, wb_id)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Sheets", stats.get("sheets", 0))
    c2.metric("Sections", stats.get("sections", 0))
    c3.metric("Cells", f"{stats.get('cells', 0):,}")
    c4.metric("公式 Cells", f"{stats.get('formulas', 0):,}")
    c5.metric("依赖关系", f"{stats.get('deps', 0):,}")

    st.divider()

    col_left, col_right = st.columns(2)

    # --- Section category distribution ---
    with col_left:
        st.subheader("Section 业务分类分布")
        cat_rows = get_section_category_distribution(client)
        if cat_rows:
            import pandas as pd
            df_cat = pd.DataFrame(cat_rows)
            df_cat["category_label"] = df_cat["category"].map(
                lambda x: _CATEGORY_LABELS.get(x, x)
            )
            df_cat = df_cat.set_index("category_label")[["count"]]
            st.bar_chart(df_cat)
        else:
            st.info("暂无分类数据（需使用 LLM 模式解析）。")

    # --- Sheet dependency heatmap ---
    with col_right:
        st.subheader("跨 Sheet 依赖热力图")
        matrix = get_sheet_dependency_matrix(client)
        if matrix:
            import pandas as pd
            sheets = list_sheets(client, wb_id)
            sheet_ids = [s["id"] for s in sheets]
            df_heat = pd.DataFrame(0, index=sheet_ids, columns=sheet_ids)
            for (src, tgt), cnt in matrix.items():
                if src in df_heat.index and tgt in df_heat.columns:
                    df_heat.loc[src, tgt] = cnt
            try:
                import plotly.express as px
                # Shorten labels for display
                short = {s: s.split("_")[-1] if "_" in s else s for s in sheet_ids}
                df_heat.index = [short.get(s, s) for s in df_heat.index]
                df_heat.columns = [short.get(s, s) for s in df_heat.columns]
                fig = px.imshow(
                    df_heat,
                    color_continuous_scale="Blues",
                    labels={"color": "依赖数"},
                    aspect="auto",
                )
                fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=350)
                st.plotly_chart(fig, use_container_width=True)
            except ImportError:
                st.dataframe(df_heat, use_container_width=True)
        else:
            st.info("暂无跨 Sheet 依赖数据。")

    st.divider()

    # --- Top impact cells ---
    st.subheader("高影响力 Cell（被依赖最多）")
    top_cells = get_top_depended_cells(client, limit=20)
    if top_cells:
        import pandas as pd
        df_top = pd.DataFrame(top_cells)
        df_top.columns = ["Cell ID", "标签", "Sheet", "当前值", "下游依赖数"]

        for i, row in df_top.iterrows():
            c1, c2, c3, c4, c5, c6 = st.columns([3, 3, 2, 2, 1, 1])
            c1.write(f"`{row['Cell ID']}`")
            c2.write(row["标签"] or "—")
            c3.write(row["Sheet"])
            c4.write(str(row["当前值"]))
            c5.write(f"**{row['下游依赖数']}**")
            with c6:
                if st.button("图谱", key=f"top_graph_{i}"):
                    st.session_state["active_cell"] = row["Cell ID"]
                    navigate_to("graph_view")
    else:
        st.info("暂无数据。")

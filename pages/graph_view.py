"""Graph Browser page — enhanced with autocomplete, legend, cross-sheet view."""
import streamlit as st

from graph.neo4j_client import Neo4jClient
from graph.queries import get_cell_autocomplete, list_sheets, get_sheet_sections
from pages import navigate_to

_LEGEND_HTML = """
<div style="position:fixed;bottom:12px;right:12px;background:#1a1a2e;
     border:1px solid #444;padding:10px 14px;border-radius:8px;font-size:13px;z-index:999;">
  <div style="color:#fff;font-weight:bold;margin-bottom:6px;">图例</div>
  <div><span style="color:#50E3C2;font-size:16px;">●</span>&nbsp;表头 Cell</div>
  <div><span style="color:#D0021B;font-size:16px;">●</span>&nbsp;公式 Cell</div>
  <div><span style="color:#9B9B9B;font-size:16px;">●</span>&nbsp;数值 Cell</div>
  <div><span style="color:#F5A623;font-size:16px;">●</span>&nbsp;Section</div>
  <div><span style="color:#7ED321;font-size:16px;">●</span>&nbsp;Sheet</div>
  <div><span style="color:#FFD700;font-size:16px;">●</span>&nbsp;选中 Cell</div>
</div>
"""


def _inject_legend(html: str) -> str:
    return html.replace("</body>", _LEGEND_HTML + "</body>")


def _render_html(html_path: str, height: int = 700) -> None:
    with open(html_path, encoding="utf-8") as f:
        html = _inject_legend(f.read())
    st.components.v1.html(html, height=height, scrolling=True)


def render(client: Neo4jClient) -> None:
    st.title("🕸️ 图谱浏览")

    if not client.verify_connectivity():
        st.error("无法连接 Neo4j，请检查配置。")
        return

    sheets = client.run("MATCH (s:Sheet) RETURN s.id AS id ORDER BY s.index")
    sheet_ids = [r["id"] for r in sheets]

    if not sheet_ids:
        st.warning("Neo4j 中暂无数据，请先上传并解析 Excel。")
        return

    view_mode = st.radio(
        "视图模式",
        ["Sheet 概览", "Section 详情", "Cell 邻域", "跨 Sheet 依赖"],
        horizontal=True,
    )

    # Pre-fill cell ID from session state (cross-page navigation)
    prefill_cell = st.session_state.pop("active_cell", None) or ""

    if view_mode == "Sheet 概览":
        selected_sheet = st.selectbox("选择 Sheet", sheet_ids, key="gv_sheet_overview")
        max_cells = st.slider("最多显示 Cell 数", 50, 500, 200, 50)
        if st.button("生成图谱", type="primary"):
            from viz.pyvis_renderer import render_sheet_overview
            with st.spinner("渲染中…"):
                html_path = render_sheet_overview(client, selected_sheet, max_cells=max_cells)
            _render_html(html_path)

    elif view_mode == "Section 详情":
        selected_sheet = st.selectbox("选择 Sheet", sheet_ids, key="gv_sheet_sec")
        secs = client.run(
            "MATCH (s:Sheet {id: $sid})-[:HAS_SECTION]->(sec:Section) RETURN sec.id AS id, sec.name AS name, sec.category AS category",
            sid=selected_sheet,
        )
        if not secs:
            st.info("该 Sheet 暂无 Section 数据。")
            return
        sec_options = {
            f"{r['name']} [{r['category'] or '未分类'}]": r["id"] for r in secs
        }
        selected_sec_label = st.selectbox("选择 Section", list(sec_options.keys()))
        selected_sec_id = sec_options[selected_sec_label]
        if st.button("生成图谱", type="primary"):
            from viz.pyvis_renderer import render_section_graph
            with st.spinner("渲染中…"):
                html_path = render_section_graph(client, selected_sec_id)
            if html_path:
                _render_html(html_path, height=650)
            else:
                st.warning("该 Section 无 Cell 数据。")

    elif view_mode == "Cell 邻域":
        # Autocomplete: search as you type
        search_prefix = st.text_input(
            "搜索 Cell（输入标签或 ID 关键词）",
            value=prefill_cell,
            key="gv_cell_search",
        )
        cell_options = []
        if search_prefix:
            results = get_cell_autocomplete(client, search_prefix, limit=30)
            cell_options = [
                f"{r['label'] or r['id']}  ({r['id']})" for r in results
            ]

        if cell_options:
            selected_label = st.selectbox("选择 Cell", cell_options, key="gv_cell_sel")
            # Extract cell_id from "label (id)" format
            cell_id_input = selected_label.split("(")[-1].rstrip(")")
        else:
            cell_id_input = st.text_input(
                "或直接输入 Cell ID",
                value=prefill_cell,
                placeholder="参数输入表_4_I",
                key="gv_cell_direct",
            )

        depth = st.slider("依赖深度", 1, 4, 2)

        if cell_id_input and st.button("生成图谱", type="primary"):
            from viz.pyvis_renderer import render_cell_neighborhood
            with st.spinner("渲染中…"):
                html_path = render_cell_neighborhood(client, cell_id_input, depth=depth)
            _render_html(html_path, height=650)

            # Link to simulation
            st.divider()
            if st.button("🔄 对此 Cell 进行变更模拟", key="gv_to_sim"):
                st.session_state["active_cell"] = cell_id_input
                navigate_to("simulation")

    elif view_mode == "跨 Sheet 依赖":
        if st.button("生成跨 Sheet 依赖图", type="primary"):
            from viz.pyvis_renderer import render_cross_sheet_graph
            with st.spinner("渲染中…"):
                html_path = render_cross_sheet_graph(client)
            if html_path:
                _render_html(html_path, height=600)
            else:
                st.warning("暂无跨 Sheet 依赖数据。")

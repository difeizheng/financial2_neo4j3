"""Financial Model Knowledge Graph — Streamlit App."""
import os
import tempfile
import streamlit as st

from config import OUTPUT_DIR, DATA_DIR
from task_manager.sqlite_manager import init_db, create_task, list_tasks, update_task, delete_task
from graph.neo4j_client import Neo4jClient

st.set_page_config(
    page_title="财务模型知识图谱",
    page_icon="📊",
    layout="wide",
)

init_db()


@st.cache_resource
def get_neo4j() -> Neo4jClient:
    return Neo4jClient()


# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------
page = st.sidebar.selectbox(
    "导航",
    ["📤 上传解析", "📋 任务列表", "🕸️ 图谱浏览", "🔄 变更模拟"],
)

# ---------------------------------------------------------------------------
# Page: Upload
# ---------------------------------------------------------------------------
if page == "📤 上传解析":
    st.title("上传财务模型 Excel")

    uploaded = st.file_uploader("选择 Excel 文件", type=["xlsx", "xls"])
    col1, col2, col3 = st.columns(3)
    with col1:
        import_neo4j = st.checkbox("解析后导入 Neo4j", value=True)
    with col2:
        use_llm = st.checkbox("LLM 智能分区识别", value=False,
                              help="使用 SiliconFlow DeepSeek-V3 识别表结构，需配置 API Key")
    with col3:
        sheet_filter = st.text_input("指定 Sheet（逗号分隔，留空=全部）", "")

    if uploaded and st.button("开始解析", type="primary"):
        # Save uploaded file
        os.makedirs(DATA_DIR, exist_ok=True)
        save_path = os.path.join(DATA_DIR, uploaded.name)
        with open(save_path, "wb") as f:
            f.write(uploaded.getbuffer())

        sheets = [s.strip() for s in sheet_filter.split(",") if s.strip()] or None
        task_id = create_task(uploaded.name, save_path, sheets)
        update_task(task_id, status="running")

        progress = st.progress(0, text="解析中…")
        try:
            from parser.excel_reader import parse_workbook
            from export.json_exporter import export_json

            llm_provider = None
            if use_llm:
                try:
                    from llm import get_provider
                    llm_provider = get_provider()
                    st.info(f"LLM: {llm_provider.name()}")
                except Exception as e:
                    st.warning(f"LLM 初始化失败，回退到规则模式：{e}")

            wb = parse_workbook(save_path, sheet_names=sheets, llm_provider=llm_provider)
            progress.progress(40, text="生成 JSON…")

            nodes_path, edges_path = export_json(wb, OUTPUT_DIR)
            progress.progress(70, text="JSON 已生成")

            total_cells = sum(len(getattr(s, "_cells") or []) for s in wb.sheets)
            total_deps = sum(
                len(c.formula_refs or [])
                for s in wb.sheets
                for c in (getattr(s, "_cells") or [])
            )

            if import_neo4j:
                progress.progress(75, text="导入 Neo4j…")
                from graph.importer import import_from_json
                client = get_neo4j()
                counts = import_from_json(nodes_path, edges_path, client)
                workbook_id = wb.id
                update_task(task_id, status="done", workbook_id=workbook_id,
                            cell_count=total_cells, dep_count=total_deps)
                progress.progress(100, text="完成")
                st.success(f"✅ 导入完成：{total_cells} 个节点，{total_deps} 条依赖关系")
                st.json(counts)
            else:
                update_task(task_id, status="done",
                            cell_count=total_cells, dep_count=total_deps)
                progress.progress(100, text="完成")
                st.success(f"✅ 解析完成：{total_cells} 个节点，{total_deps} 条依赖关系")

        except Exception as e:
            import traceback
            update_task(task_id, status="error", error_msg=str(e))
            st.error(f"❌ 解析失败：{e}")
            st.code(traceback.format_exc())

# ---------------------------------------------------------------------------
# Page: Tasks
# ---------------------------------------------------------------------------
elif page == "📋 任务列表":
    st.title("解析任务列表")

    if st.button("🔄 刷新"):
        st.rerun()

    tasks = list_tasks()
    if not tasks:
        st.info("暂无任务，请先上传 Excel 文件。")
    else:
        for t in tasks:
            status_icon = {"pending": "⏳", "running": "🔄", "done": "✅", "error": "❌"}.get(t["status"], "❓")
            with st.expander(f"{status_icon} {t['filename']}  —  {t['created_at'][:19]}"):
                col1, col2, col3 = st.columns(3)
                col1.metric("状态", t["status"])
                col2.metric("Cell 数", t["cell_count"] or "—")
                col3.metric("依赖数", t["dep_count"] or "—")
                if t.get("error_msg"):
                    st.error(t["error_msg"])
                if t.get("workbook_id"):
                    st.caption(f"Workbook ID: {t['workbook_id']}")
                if st.button("删除", key=f"del_{t['id']}"):
                    delete_task(t["id"])
                    st.rerun()

# ---------------------------------------------------------------------------
# Page: Graph Browser
# ---------------------------------------------------------------------------
elif page == "🕸️ 图谱浏览":
    st.title("图谱浏览")

    client = get_neo4j()
    if not client.verify_connectivity():
        st.error("无法连接 Neo4j，请检查配置。")
        st.stop()

    view_mode = st.radio("视图模式", ["Sheet 概览", "Section 详情", "Cell 邻域"], horizontal=True)

    # Fetch available sheets
    sheets = client.run("MATCH (s:Sheet) RETURN s.id AS id ORDER BY s.index")
    sheet_ids = [r["id"] for r in sheets]

    if not sheet_ids:
        st.warning("Neo4j 中暂无数据，请先上传并解析 Excel。")
        st.stop()

    selected_sheet = st.selectbox("选择 Sheet", sheet_ids)

    if view_mode == "Sheet 概览":
        max_cells = st.slider("最多显示 Cell 数", 50, 500, 200, 50)
        if st.button("生成图谱", type="primary"):
            from viz.pyvis_renderer import render_sheet_overview
            with st.spinner("渲染中…"):
                html_path = render_sheet_overview(client, selected_sheet, max_cells=max_cells)
            with open(html_path, encoding="utf-8") as f:
                st.components.v1.html(f.read(), height=750, scrolling=True)

    elif view_mode == "Section 详情":
        secs = client.run(
            "MATCH (s:Sheet {id: $sid})-[:HAS_SECTION]->(sec:Section) RETURN sec.id AS id, sec.name AS name",
            sid=selected_sheet,
        )
        sec_options = {r["name"]: r["id"] for r in secs}
        if not sec_options:
            st.info("该 Sheet 暂无 Section 数据。")
        else:
            selected_sec_name = st.selectbox("选择 Section", list(sec_options.keys()))
            selected_sec_id = sec_options[selected_sec_name]
            if st.button("生成图谱", type="primary"):
                from viz.pyvis_renderer import render_section_graph
                with st.spinner("渲染中…"):
                    html_path = render_section_graph(client, selected_sec_id)
                if html_path:
                    with open(html_path, encoding="utf-8") as f:
                        st.components.v1.html(f.read(), height=650, scrolling=True)
                else:
                    st.warning("该 Section 无 Cell 数据。")

    elif view_mode == "Cell 邻域":
        cell_id_input = st.text_input("输入 Cell ID（如 参数输入表_4_I）")
        depth = st.slider("依赖深度", 1, 4, 2)
        if cell_id_input and st.button("生成图谱", type="primary"):
            from viz.pyvis_renderer import render_cell_neighborhood
            with st.spinner("渲染中…"):
                html_path = render_cell_neighborhood(client, cell_id_input, depth=depth)
            with open(html_path, encoding="utf-8") as f:
                st.components.v1.html(f.read(), height=650, scrolling=True)

# ---------------------------------------------------------------------------
# Page: Change Simulation
# ---------------------------------------------------------------------------
elif page == "🔄 变更模拟":
    st.title("变更传播模拟")
    st.caption("修改某个 Cell 的值，查看图谱中哪些 Cell 会受到影响并自动重算。")

    client = get_neo4j()
    if not client.verify_connectivity():
        st.error("无法连接 Neo4j，请检查配置。")
        st.stop()

    col1, col2 = st.columns(2)
    with col1:
        cell_id = st.text_input("Cell ID", placeholder="参数输入表_9_I")
    with col2:
        new_value_str = st.text_input("新值", placeholder="89")

    if cell_id:
        rows = client.run(
            "MATCH (c:Cell {id: $id}) RETURN c.value AS value, c.formula_raw AS formula, c.label AS label",
            id=cell_id,
        )
        if rows:
            r = rows[0]
            st.info(f"**{r['label'] or cell_id}** | 当前值: `{r['value']}` | 公式: `{r['formula'] or '无'}`")
        else:
            st.warning("未找到该 Cell，请检查 ID。")

    dry_run = st.checkbox("仅预览影响范围（不写入 Neo4j）", value=True)

    if cell_id and new_value_str and st.button("执行变更", type="primary"):
        try:
            new_value = float(new_value_str) if "." in new_value_str else int(new_value_str)
        except ValueError:
            new_value = new_value_str

        from graph.propagator import Propagator
        prop = Propagator(client)

        # Store in session_state for checkbox rerun
        st.session_state["change_cell_id"] = cell_id
        st.session_state["change_new_value"] = new_value
        st.session_state["change_dry_run"] = dry_run

        with st.spinner("计算传播影响…"):
            if dry_run:
                downstream = prop._find_downstream([cell_id])
                st.session_state["change_downstream"] = downstream
                st.success(f"影响范围：**{len(downstream)}** 个下游 Cell")
                if downstream:
                    sample = list(downstream)[:20]
                    rows = client.run(
                        "MATCH (c:Cell) WHERE c.id IN $ids RETURN c.id AS id, c.label AS label, c.value AS value, c.formula_raw AS formula",
                        ids=sample,
                    )
                    import pandas as pd
                    df = pd.DataFrame(rows)
                    st.dataframe(df, use_container_width=True)
                    if len(downstream) > 20:
                        st.caption(f"…仅显示前 20 条，共 {len(downstream)} 条")
            else:
                updated = prop.propagate({cell_id: new_value})
                st.success(f"✅ 已更新 **{len(updated)}** 个 Cell")
                import pandas as pd
                df = pd.DataFrame([{"cell_id": k, "new_value": v} for k, v in updated.items()])
                st.dataframe(df, use_container_width=True)
                # Clear session state after real execution
                st.session_state.pop("change_downstream", None)

    # Visualize impact (outside button click, uses session_state)
    if st.session_state.get("change_downstream") and st.session_state.get("change_dry_run"):
        if st.checkbox("可视化影响范围", key="viz_checkbox"):
            viz_cell_id = st.session_state.get("change_cell_id", "")
            if viz_cell_id:
                from viz.pyvis_renderer import render_cell_neighborhood
                html_path = render_cell_neighborhood(client, viz_cell_id, depth=3)
                if html_path:
                    with open(html_path, encoding="utf-8") as f:
                        st.components.v1.html(f.read(), height=600, scrolling=True)

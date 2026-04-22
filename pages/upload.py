"""Upload & Parse page."""
import os
import streamlit as st

from config import OUTPUT_DIR, DATA_DIR
from graph.neo4j_client import Neo4jClient
from task_manager.sqlite_manager import create_task, update_task


def render(client: Neo4jClient) -> None:
    st.title("上传财务模型 Excel")

    uploaded = st.file_uploader("选择 Excel 文件", type=["xlsx", "xls"])
    col1, col2, col3 = st.columns(3)
    with col1:
        import_neo4j = st.checkbox("解析后导入 Neo4j", value=True)
    with col2:
        use_llm = st.checkbox(
            "LLM 智能分区识别", value=False,
            help="使用 SiliconFlow DeepSeek-V3 识别表结构，需配置 API Key",
        )
    with col3:
        sheet_filter = st.text_input("指定 Sheet（逗号分隔，留空=全部）", "")

    if uploaded and st.button("开始解析", type="primary"):
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
                counts = import_from_json(nodes_path, edges_path, client)
                update_task(task_id, status="done", workbook_id=wb.id,
                            cell_count=total_cells, dep_count=total_deps)
                progress.progress(100, text="完成")
                st.success(f"✅ 导入完成：{total_cells} 个节点，{total_deps} 条依赖关系")
                st.json(counts)
                st.session_state["active_workbook"] = wb.id
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

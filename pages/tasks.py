"""Task List page."""
import streamlit as st

from graph.neo4j_client import Neo4jClient
from pages import navigate_to
from task_manager.sqlite_manager import list_tasks, delete_task


def render(client: Neo4jClient) -> None:
    st.title("解析任务列表")

    if st.button("🔄 刷新"):
        st.rerun()

    tasks = list_tasks()
    if not tasks:
        st.info("暂无任务，请先上传 Excel 文件。")
        return

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

            btn_col1, btn_col2, btn_col3 = st.columns(3)
            with btn_col1:
                if st.button("删除", key=f"del_{t['id']}"):
                    delete_task(t["id"])
                    st.rerun()
            if t.get("workbook_id"):
                with btn_col2:
                    if st.button("📊 查看仪表盘", key=f"dash_{t['id']}"):
                        st.session_state["active_workbook"] = t["workbook_id"]
                        navigate_to("dashboard")
                with btn_col3:
                    if st.button("🕸️ 查看图谱", key=f"graph_{t['id']}"):
                        st.session_state["active_workbook"] = t["workbook_id"]
                        navigate_to("graph_view")

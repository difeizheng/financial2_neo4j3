"""Financial Model Knowledge Graph — Streamlit App (router)."""
import streamlit as st

from graph.neo4j_client import Neo4jClient
from task_manager.sqlite_manager import init_db
from pages import init_session_state

st.set_page_config(
    page_title="财务模型知识图谱",
    page_icon="📊",
    layout="wide",
)

init_db()
init_session_state()


@st.cache_resource
def get_neo4j() -> Neo4jClient:
    return Neo4jClient()


# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------
PAGES = {
    "📤 上传解析": "upload",
    "📋 任务列表": "tasks",
    "📊 仪表盘": "dashboard",
    "🔍 数据浏览": "browser",
    "🕸️ 图谱浏览": "graph_view",
    "🔄 变更模拟": "simulation",
}

# Handle programmatic navigation
if st.session_state.get("navigate_to"):
    target = st.session_state.pop("navigate_to")
    label = next((k for k, v in PAGES.items() if v == target), None)
    if label:
        st.session_state["_current_page"] = label

default_page = st.session_state.get("_current_page", "📤 上传解析")
page_label = st.sidebar.selectbox("导航", list(PAGES.keys()),
                                   index=list(PAGES.keys()).index(default_page))
st.session_state["_current_page"] = page_label

# ---------------------------------------------------------------------------
# Sidebar: workbook context
# ---------------------------------------------------------------------------
client = get_neo4j()
if client.verify_connectivity():
    wbs = client.run("MATCH (w:Workbook) RETURN w.id AS id, w.name AS name ORDER BY w.name")
    if wbs:
        wb_options = {(r["name"] or r["id"]): r["id"] for r in wbs}
        selected_wb_label = st.sidebar.selectbox("工作簿", list(wb_options.keys()))
        st.session_state["active_workbook"] = wb_options[selected_wb_label]
else:
    st.sidebar.warning("Neo4j 未连接")

# ---------------------------------------------------------------------------
# Page dispatch
# ---------------------------------------------------------------------------
page_key = PAGES[page_label]

if page_key == "upload":
    from pages.upload import render
elif page_key == "tasks":
    from pages.tasks import render
elif page_key == "dashboard":
    from pages.dashboard import render
elif page_key == "browser":
    from pages.browser import render
elif page_key == "graph_view":
    from pages.graph_view import render
else:
    from pages.simulation import render

render(client)

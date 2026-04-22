"""Page navigation helpers using st.session_state."""
import streamlit as st

PAGE_NAMES = [
    "📤 上传解析",
    "📋 任务列表",
    "📊 仪表盘",
    "🔍 数据浏览",
    "🕸️ 图谱浏览",
    "🔄 变更模拟",
]


def navigate_to(page: str, **params) -> None:
    st.session_state["navigate_to"] = page
    st.session_state["navigate_params"] = params
    st.rerun()


def init_session_state() -> None:
    defaults = {
        "active_workbook": None,
        "active_sheet": None,
        "active_cell": None,
        "navigate_to": None,
        "navigate_params": {},
        "sim_changes": {},
        "sim_results": None,
        "sim_undo_stack": [],
        "change_downstream": None,
        "change_cell_id": None,
        "change_dry_run": True,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

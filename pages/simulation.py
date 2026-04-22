"""Change Simulation page — batch changes, before/after comparison, scenarios, undo."""
import json
import streamlit as st
import pandas as pd

from graph.neo4j_client import Neo4jClient
from graph.queries import get_cell_basic, get_cell_autocomplete
from pages import navigate_to
from task_manager.scenario_manager import list_scenarios, save_scenario, delete_scenario


def _parse_value(s: str):
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return s


def _fetch_before_values(client: Neo4jClient, cell_ids: list[str]) -> dict:
    if not cell_ids:
        return {}
    rows = client.run(
        "MATCH (c:Cell) WHERE c.id IN $ids RETURN c.id AS id, c.value AS value, c.label AS label, c.formula_raw AS formula",
        ids=cell_ids,
    )
    return {r["id"]: r for r in rows}


def render(client: Neo4jClient) -> None:
    st.title("🔄 变更传播模拟")
    st.caption("修改 Cell 值，查看下游影响并自动重算。支持批量变更和场景管理。")

    if not client.verify_connectivity():
        st.error("无法连接 Neo4j，请检查配置。")
        return

    # Pre-fill from cross-page navigation
    prefill_cell = st.session_state.pop("active_cell", None)
    if prefill_cell and prefill_cell not in [c["id"] for c in st.session_state.get("sim_changes_list", [])]:
        if "sim_changes_list" not in st.session_state:
            st.session_state["sim_changes_list"] = []
        st.session_state["sim_changes_list"].append({"id": prefill_cell, "value": ""})

    # --- Scenario load ---
    with st.expander("📂 加载已保存场景", expanded=False):
        scenarios = list_scenarios()
        if scenarios:
            sel_scenario = st.selectbox(
                "选择场景",
                options=scenarios,
                format_func=lambda s: f"{s['name']} ({s['created_at'][:10]})",
                key="sim_scenario_sel",
            )
            sc1, sc2 = st.columns(2)
            with sc1:
                if st.button("加载场景", key="sim_load_scenario"):
                    changes = json.loads(sel_scenario["changes_json"])
                    st.session_state["sim_changes_list"] = [
                        {"id": k, "value": str(v)} for k, v in changes.items()
                    ]
                    st.rerun()
            with sc2:
                if st.button("删除场景", key="sim_del_scenario"):
                    delete_scenario(sel_scenario["id"])
                    st.rerun()
        else:
            st.info("暂无保存的场景。")

    st.divider()

    # --- Batch change editor ---
    st.subheader("变更列表")

    if "sim_changes_list" not in st.session_state:
        st.session_state["sim_changes_list"] = [{"id": "", "value": ""}]

    changes_list = st.session_state["sim_changes_list"]

    to_remove = []
    for i, entry in enumerate(changes_list):
        c1, c2, c3 = st.columns([4, 3, 1])
        with c1:
            search_key = f"sim_search_{i}"
            search_val = st.text_input("搜索 Cell", value=entry.get("id", ""), key=search_key, label_visibility="collapsed", placeholder="输入 Cell ID 或标签关键词")
            if search_val and search_val != entry.get("id", ""):
                suggestions = get_cell_autocomplete(client, search_val, limit=20)
                if suggestions:
                    opts = [f"{r['label'] or r['id']}  ({r['id']})" for r in suggestions]
                    sel = st.selectbox("", opts, key=f"sim_sel_{i}", label_visibility="collapsed")
                    entry["id"] = sel.split("(")[-1].rstrip(")")
                else:
                    entry["id"] = search_val
        with c2:
            entry["value"] = st.text_input("新值", value=entry.get("value", ""), key=f"sim_val_{i}", label_visibility="collapsed", placeholder="新值")
        with c3:
            if st.button("✕", key=f"sim_rm_{i}"):
                to_remove.append(i)

        # Show current cell info
        if entry.get("id"):
            cell_info = get_cell_basic(client, entry["id"])
            if cell_info:
                st.caption(f"  当前值: `{cell_info['value']}` | 公式: `{cell_info['formula'] or '无'}` | 标签: {cell_info['label'] or '—'}")
            else:
                st.caption("  ⚠️ 未找到此 Cell")

    for i in reversed(to_remove):
        changes_list.pop(i)

    if st.button("➕ 添加变更行"):
        changes_list.append({"id": "", "value": ""})
        st.rerun()

    # Build changes dict
    changes: dict = {}
    for entry in changes_list:
        if entry.get("id") and entry.get("value") != "":
            changes[entry["id"]] = _parse_value(entry["value"])

    st.divider()

    # --- Execution options ---
    dry_run = st.checkbox("仅预览影响范围（不写入 Neo4j）", value=True)

    col_exec, col_undo = st.columns(2)
    with col_exec:
        exec_btn = st.button("▶ 执行变更", type="primary", disabled=not changes)
    with col_undo:
        undo_btn = st.button(
            "↩ 撤销上次变更",
            disabled=not st.session_state.get("sim_undo_stack"),
        )

    # --- Undo ---
    if undo_btn and st.session_state.get("sim_undo_stack"):
        undo_changes = st.session_state["sim_undo_stack"].pop()
        from graph.propagator import Propagator
        prop = Propagator(client)
        with st.spinner("撤销中…"):
            prop.propagate(undo_changes)
        st.success(f"✅ 已撤销，恢复 {len(undo_changes)} 个 Cell 的原值")
        st.rerun()

    # --- Execute ---
    if exec_btn and changes:
        from graph.propagator import Propagator
        prop = Propagator(client)

        with st.spinner("计算传播影响…"):
            if dry_run:
                result = prop.dry_run_with_comparison(changes)
                st.session_state["sim_results"] = result
                st.session_state["change_dry_run"] = True
            else:
                # Snapshot before values for undo
                all_downstream = prop._find_downstream(list(changes.keys()))
                all_ids = list(changes.keys()) + list(all_downstream)
                before_snap = {r["id"]: r["value"] for r in client.run(
                    "MATCH (c:Cell) WHERE c.id IN $ids RETURN c.id AS id, c.value AS value",
                    ids=all_ids,
                )}
                updated, topo_order = prop.propagate_with_trace(changes)
                # Push undo snapshot (only cells that changed)
                undo_snap = {cid: before_snap[cid] for cid in updated if cid in before_snap}
                st.session_state["sim_undo_stack"].append(undo_snap)
                st.session_state["sim_results"] = {
                    cid: {"old": before_snap.get(cid), "new": v, "formula": None}
                    for cid, v in updated.items()
                }
                st.session_state["change_dry_run"] = False
                st.session_state["sim_topo_order"] = topo_order
                st.success(f"✅ 已更新 **{len(updated)}** 个 Cell")

    # --- Results display ---
    results = st.session_state.get("sim_results")
    if results:
        is_dry = st.session_state.get("change_dry_run", True)
        label = "预览影响范围" if is_dry else "变更结果"
        st.subheader(f"📊 {label}（{len(results)} 个 Cell）")

        # Fetch labels for display
        ids = list(results.keys())
        label_rows = client.run(
            "MATCH (c:Cell) WHERE c.id IN $ids RETURN c.id AS id, c.label AS label, c.formula_raw AS formula",
            ids=ids[:200],
        )
        label_map = {r["id"]: r for r in label_rows}

        rows_data = []
        for cid, info in list(results.items())[:200]:
            old_val = info.get("old")
            new_val = info.get("new")
            try:
                delta = float(new_val) - float(old_val) if old_val is not None and new_val is not None else None
            except (TypeError, ValueError):
                delta = None
            rows_data.append({
                "Cell ID": cid,
                "标签": label_map.get(cid, {}).get("label") or "—",
                "旧值": old_val,
                "新值": new_val,
                "变化量": f"{delta:+.4g}" if delta is not None else "—",
                "公式": label_map.get(cid, {}).get("formula") or "—",
            })

        df = pd.DataFrame(rows_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

        if len(results) > 200:
            st.caption(f"仅显示前 200 条，共 {len(results)} 条")

        # Visualization
        if st.checkbox("可视化影响范围", key="sim_viz_checkbox"):
            seed_ids = list(changes.keys())
            if seed_ids:
                from viz.pyvis_renderer import render_cell_neighborhood
                html_path = render_cell_neighborhood(client, seed_ids[0], depth=3)
                if html_path:
                    with open(html_path, encoding="utf-8") as f:
                        st.components.v1.html(f.read(), height=600, scrolling=True)

        # Calculation chain (real run only)
        topo = st.session_state.get("sim_topo_order")
        if topo and not is_dry:
            if st.checkbox("查看计算链", key="sim_chain_checkbox"):
                from viz.pyvis_renderer import render_propagation_chain
                html_path = render_propagation_chain(client, topo, list(changes.keys()))
                if html_path:
                    with open(html_path, encoding="utf-8") as f:
                        st.components.v1.html(f.read(), height=500, scrolling=True)

        # Save scenario
        st.divider()
        with st.expander("💾 保存为场景"):
            sc_name = st.text_input("场景名称", key="sim_save_name")
            sc_desc = st.text_area("描述（可选）", key="sim_save_desc", height=60)
            if st.button("保存场景", key="sim_save_btn") and sc_name:
                save_scenario(
                    name=sc_name,
                    changes=changes,
                    description=sc_desc,
                    workbook_id=st.session_state.get("active_workbook"),
                )
                st.success("场景已保存。")

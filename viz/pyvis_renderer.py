"""pyvis-based interactive graph renderer."""
import os
import tempfile
from typing import Optional

from pyvis.network import Network

from graph.neo4j_client import Neo4jClient

# Node color palette by type
_COLORS = {
    "Workbook": "#4A90D9",
    "Sheet":    "#7ED321",
    "Section":  "#F5A623",
    "Cell_formula": "#D0021B",
    "Cell_value":   "#9B9B9B",
    "Cell_head":    "#50E3C2",
}


def _cell_color(cell: dict) -> str:
    if cell.get("is_head"):
        return _COLORS["Cell_head"]
    if cell.get("formula_raw"):
        return _COLORS["Cell_formula"]
    return _COLORS["Cell_value"]


def _cell_label(cell: dict) -> str:
    label = cell.get("label") or cell.get("id", "")
    val = cell.get("value")
    unit = cell.get("unit") or ""
    if val is not None and not cell.get("is_head"):
        return f"{label}\n{val} {unit}".strip()
    return str(label)


def _cell_title(cell: dict) -> str:
    parts = [
        f"ID: {cell.get('id')}",
        f"Sheet: {cell.get('sheet')}",
        f"Row/Col: {cell.get('row')}/{cell.get('col')}",
        f"Value: {cell.get('value')}",
        f"Formula: {cell.get('formula_raw') or '—'}",
        f"Section: {cell.get('section_id') or '—'}",
        f"Unit: {cell.get('unit') or '—'}",
        f"Description: {cell.get('description') or '—'}",
    ]
    return "\n".join(parts)


def render_section_graph(client: Neo4jClient,
                         section_id: str,
                         output_path: Optional[str] = None,
                         height: str = "600px") -> str:
    """Render the dependency graph for all cells in a section.

    Returns the path to the generated HTML file.
    """
    # Fetch cells in section
    cells = client.run(
        """
        MATCH (sec:Section {id: $sid})-[:CONTAINS_CELL]->(c:Cell)
        RETURN c {.*} AS cell
        """,
        sid=section_id,
    )
    if not cells:
        return ""

    cell_ids = [r["cell"]["id"] for r in cells]

    # Fetch dependency edges among these cells (and one hop out)
    edges = client.run(
        """
        MATCH (src:Cell)-[:DEPENDS_ON]->(tgt:Cell)
        WHERE src.id IN $ids
        RETURN src.id AS src, tgt.id AS tgt, tgt {.*} AS tgt_cell
        """,
        ids=cell_ids,
    )

    net = Network(height=height, width="100%", directed=True,
                  bgcolor="#1a1a2e", font_color="white")
    net.set_options("""
    {
      "physics": {"stabilization": {"iterations": 100}},
      "edges": {"arrows": {"to": {"enabled": true, "scaleFactor": 0.5}},
                "color": {"color": "#aaaaaa"}},
      "nodes": {"font": {"size": 11}}
    }
    """)

    added_nodes: set[str] = set()

    def add_cell_node(cell_dict: dict) -> None:
        nid = cell_dict["id"]
        if nid in added_nodes:
            return
        added_nodes.add(nid)
        net.add_node(
            nid,
            label=_cell_label(cell_dict),
            title=_cell_title(cell_dict),
            color=_cell_color(cell_dict),
            size=15 if cell_dict.get("formula_raw") else 10,
        )

    for r in cells:
        add_cell_node(r["cell"])

    for r in edges:
        tgt_cell = r["tgt_cell"]
        add_cell_node(tgt_cell)
        net.add_edge(r["src"], r["tgt"], color="#ff6b6b")

    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False)
        output_path = tmp.name

    net.save_graph(output_path)
    return output_path


def render_sheet_overview(client: Neo4jClient,
                          sheet_id: str,
                          max_cells: int = 300,
                          output_path: Optional[str] = None,
                          height: str = "700px") -> str:
    """Render a high-level overview: Sheet → Sections → sampled Cells."""
    sections = client.run(
        "MATCH (s:Sheet {id: $sid})-[:HAS_SECTION]->(sec:Section) RETURN sec {.*} AS sec",
        sid=sheet_id,
    )

    net = Network(height=height, width="100%", directed=True,
                  bgcolor="#1a1a2e", font_color="white")
    net.set_options("""
    {
      "layout": {"hierarchical": {"enabled": true, "direction": "LR", "sortMethod": "directed"}},
      "physics": {"enabled": false},
      "edges": {"arrows": {"to": {"enabled": true, "scaleFactor": 0.4}}}
    }
    """)

    # Sheet node
    net.add_node(sheet_id, label=sheet_id, color=_COLORS["Sheet"], size=25, shape="box")

    cell_budget = max_cells
    for r in sections:
        sec = r["sec"]
        sec_id = sec["id"]
        net.add_node(sec_id, label=sec["name"], color=_COLORS["Section"], size=18, shape="ellipse")
        net.add_edge(sheet_id, sec_id)

        if cell_budget <= 0:
            continue

        cells = client.run(
            """
            MATCH (sec:Section {id: $sid})-[:CONTAINS_CELL]->(c:Cell)
            WHERE NOT c.is_head
            RETURN c {.*} AS cell LIMIT $lim
            """,
            sid=sec_id, lim=min(cell_budget, 30),
        )
        for cr in cells:
            c = cr["cell"]
            net.add_node(c["id"], label=_cell_label(c), title=_cell_title(c),
                         color=_cell_color(c), size=8)
            net.add_edge(sec_id, c["id"])
            cell_budget -= 1

    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False)
        output_path = tmp.name

    net.save_graph(output_path)
    return output_path


def render_cross_sheet_graph(client: Neo4jClient,
                              output_path: Optional[str] = None,
                              height: str = "600px") -> str:
    """Render sheet-level dependency graph with weighted edges."""
    rows = client.run("""
        MATCH (src:Cell)-[:DEPENDS_ON]->(tgt:Cell)
        WHERE src.sheet <> tgt.sheet
        RETURN src.sheet AS src_sheet, tgt.sheet AS tgt_sheet, count(*) AS weight
    """)

    sheets = client.run("MATCH (s:Sheet) RETURN s.id AS id")
    sheet_ids = [r["id"] for r in sheets if r["id"]]

    net = Network(height=height, width="100%", directed=True,
                  bgcolor="#1a1a2e", font_color="white")
    net.set_options("""
    {
      "physics": {"stabilization": {"iterations": 100}},
      "edges": {"arrows": {"to": {"enabled": true, "scaleFactor": 0.6}},
                "scaling": {"min": 1, "max": 10}}
    }
    """)

    for sid in sheet_ids:
        net.add_node(sid, label=sid, color=_COLORS["Sheet"], size=20, shape="box")

    for r in rows:
        src, tgt = r.get("src_sheet"), r.get("tgt_sheet")
        if not src or not tgt:
            continue
        net.add_edge(src, tgt,
                     value=r["weight"],
                     title=f"{r['weight']} 条依赖",
                     color="#F5A623")

    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False)
        output_path = tmp.name

    net.save_graph(output_path)
    return output_path


def render_propagation_chain(client: Neo4jClient,
                              topo_order: list[str],
                              changes: dict,
                              output_path: Optional[str] = None,
                              height: str = "600px") -> str:
    """Render the propagation chain in topological order."""
    if not topo_order:
        return ""

    cell_ids = list(topo_order)[:100]
    rows = client.run(
        "MATCH (c:Cell) WHERE c.id IN $ids RETURN c {.*} AS cell",
        ids=cell_ids,
    )
    cell_map = {r["cell"]["id"]: r["cell"] for r in rows}

    edges = client.run(
        """
        MATCH (src:Cell)-[:DEPENDS_ON]->(tgt:Cell)
        WHERE src.id IN $ids AND tgt.id IN $ids
        RETURN src.id AS src, tgt.id AS tgt
        """,
        ids=cell_ids,
    )

    net = Network(height=height, width="100%", directed=True,
                  bgcolor="#1a1a2e", font_color="white")
    net.set_options("""
    {
      "layout": {"hierarchical": {"enabled": true, "direction": "LR", "sortMethod": "directed"}},
      "physics": {"enabled": false},
      "edges": {"arrows": {"to": {"enabled": true, "scaleFactor": 0.5}}}
    }
    """)

    seed_ids = set(changes.keys())
    for i, cid in enumerate(cell_ids):
        cell = cell_map.get(cid, {"id": cid})
        color = "#FFD700" if cid in seed_ids else _cell_color(cell)
        net.add_node(cid, label=_cell_label(cell), title=f"#{i+1} {_cell_title(cell)}",
                     color=color, size=18 if cid in seed_ids else 12, level=i)

    for r in edges:
        net.add_edge(r["src"], r["tgt"])

    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False)
        output_path = tmp.name

    net.save_graph(output_path)
    return output_path


def render_cell_neighborhood(client: Neo4jClient,
                              cell_id: str,
                              depth: int = 2,
                              output_path: Optional[str] = None,
                              height: str = "600px") -> str:
    """Render the dependency neighborhood of a single cell (up/downstream)."""
    rows = client.run(
        """
        MATCH path = (c:Cell {id: $cid})-[:DEPENDS_ON*0..%d]-(neighbor:Cell)
        RETURN neighbor {.*} AS cell,
               startNode(relationships(path)[0]).id AS from_id,
               endNode(relationships(path)[0]).id   AS to_id
        LIMIT 200
        """ % depth,
        cid=cell_id,
    )

    # Also get the seed cell
    seed_rows = client.run("MATCH (c:Cell {id: $id}) RETURN c {.*} AS cell", id=cell_id)

    net = Network(height=height, width="100%", directed=True,
                  bgcolor="#1a1a2e", font_color="white")
    net.set_options("""
    {
      "physics": {"stabilization": {"iterations": 150}},
      "edges": {"arrows": {"to": {"enabled": true, "scaleFactor": 0.5}},
                "color": {"color": "#aaaaaa"}}
    }
    """)

    added: set[str] = set()

    def add_node(cell_dict: dict, is_seed: bool = False) -> None:
        nid = cell_dict["id"]
        if nid in added:
            return
        added.add(nid)
        color = "#FFD700" if is_seed else _cell_color(cell_dict)
        size = 22 if is_seed else 12
        net.add_node(nid, label=_cell_label(cell_dict), title=_cell_title(cell_dict),
                     color=color, size=size)

    if seed_rows:
        add_node(seed_rows[0]["cell"], is_seed=True)

    edge_set: set[tuple] = set()
    for r in rows:
        add_node(r["cell"])
        src, tgt = r.get("from_id"), r.get("to_id")
        if src and tgt and (src, tgt) not in edge_set:
            edge_set.add((src, tgt))
            net.add_edge(src, tgt)

    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False)
        output_path = tmp.name

    net.save_graph(output_path)
    return output_path

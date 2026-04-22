"""Neo4j domain query layer — all Cypher lives here."""
from typing import Any

from graph.neo4j_client import Neo4jClient


# ---------------------------------------------------------------------------
# Workbook
# ---------------------------------------------------------------------------

def list_workbooks(client: Neo4jClient) -> list[dict]:
    return client.run("MATCH (w:Workbook) RETURN w.id AS id, w.filename AS filename ORDER BY w.id")


def get_workbook_stats(client: Neo4jClient, workbook_id: str) -> dict:
    rows = client.run(
        """
        MATCH (w:Workbook {id: $wid})
        OPTIONAL MATCH (w)-[:HAS_SHEET]->(s:Sheet)
        OPTIONAL MATCH (s)-[:HAS_SECTION]->(sec:Section)
        OPTIONAL MATCH (sec)-[:CONTAINS_CELL]->(c:Cell)
        RETURN
            count(DISTINCT s)   AS sheets,
            count(DISTINCT sec) AS sections,
            count(DISTINCT c)   AS cells,
            sum(CASE WHEN c.formula_raw IS NOT NULL AND c.formula_raw <> '' THEN 1 ELSE 0 END) AS formulas
        """,
        wid=workbook_id,
    )
    stats = rows[0] if rows else {"sheets": 0, "sections": 0, "cells": 0, "formulas": 0}

    dep_rows = client.run(
        """
        MATCH (w:Workbook {id: $wid})-[:HAS_SHEET]->(s:Sheet)-[:HAS_SECTION]->(sec:Section)
              -[:CONTAINS_CELL]->(c:Cell)-[:DEPENDS_ON]->(d:Cell)
        RETURN count(*) AS deps
        """,
        wid=workbook_id,
    )
    stats["deps"] = dep_rows[0]["deps"] if dep_rows else 0
    return stats


# ---------------------------------------------------------------------------
# Sheet
# ---------------------------------------------------------------------------

def list_sheets(client: Neo4jClient, workbook_id: str | None = None) -> list[dict]:
    if workbook_id:
        return client.run(
            "MATCH (w:Workbook {id: $wid})-[:HAS_SHEET]->(s:Sheet) RETURN s.id AS id, s.index AS idx ORDER BY s.index",
            wid=workbook_id,
        )
    return client.run("MATCH (s:Sheet) RETURN s.id AS id, s.index AS idx ORDER BY s.index")


def get_sheet_sections(client: Neo4jClient, sheet_id: str) -> list[dict]:
    return client.run(
        """
        MATCH (s:Sheet {id: $sid})-[:HAS_SECTION]->(sec:Section)
        RETURN sec.id AS id, sec.name AS name, sec.category AS category,
               sec.row_start AS row_start, sec.row_end AS row_end
        ORDER BY sec.row_start
        """,
        sid=sheet_id,
    )


# ---------------------------------------------------------------------------
# Cell search + detail
# ---------------------------------------------------------------------------

def search_cells(
    client: Neo4jClient,
    query: str = "",
    filters: dict | None = None,
    page: int = 0,
    page_size: int = 50,
) -> tuple[list[dict], int]:
    """Full-text search with filters. Returns (rows, total_count)."""
    filters = filters or {}
    sheet = filters.get("sheet")
    section_id = filters.get("section_id")
    category = filters.get("category")
    value_type = filters.get("value_type")
    is_head = filters.get("is_head")

    where_clauses = []
    params: dict[str, Any] = {"skip": page * page_size, "limit": page_size}

    if query:
        where_clauses.append(
            "(c.label CONTAINS $q OR c.description CONTAINS $q "
            "OR c.formula_raw CONTAINS $q OR toString(c.value) CONTAINS $q)"
        )
        params["q"] = query
    if sheet:
        where_clauses.append("c.sheet = $sheet")
        params["sheet"] = sheet
    if section_id:
        where_clauses.append("sec.id = $section_id")
        params["section_id"] = section_id
    if category:
        where_clauses.append("sec.category = $category")
        params["category"] = category
    if value_type:
        where_clauses.append("c.value_type = $value_type")
        params["value_type"] = value_type
    if is_head is not None:
        where_clauses.append("c.is_head = $is_head")
        params["is_head"] = is_head

    where_str = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    cypher = f"""
        MATCH (c:Cell)
        OPTIONAL MATCH (sec:Section)-[:CONTAINS_CELL]->(c)
        {where_str}
        RETURN c.id AS id, c.sheet AS sheet, sec.name AS section_name,
               sec.category AS section_category, c.label AS label,
               c.value AS value, c.unit AS unit, c.formula_raw AS formula,
               c.value_type AS value_type, c.row_category AS row_category,
               c.col_category AS col_category, c.description AS description,
               c.is_head AS is_head, c.row AS row, c.col AS col
        ORDER BY c.sheet, c.row, c.col
        SKIP $skip LIMIT $limit
    """
    count_cypher = f"""
        MATCH (c:Cell)
        OPTIONAL MATCH (sec:Section)-[:CONTAINS_CELL]->(c)
        {where_str}
        RETURN count(c) AS total
    """
    count_params = {k: v for k, v in params.items() if k not in ("skip", "limit")}

    rows = client.run(cypher, **params)
    count_rows = client.run(count_cypher, **count_params)
    total = count_rows[0]["total"] if count_rows else 0
    return rows, total


def get_cell_detail(client: Neo4jClient, cell_id: str) -> dict | None:
    rows = client.run(
        """
        MATCH (c:Cell {id: $id})
        OPTIONAL MATCH (sec:Section)-[:CONTAINS_CELL]->(c)
        RETURN c {.*}, sec.name AS section_name, sec.category AS section_category
        """,
        id=cell_id,
    )
    if not rows:
        return None
    row = dict(rows[0])
    # Flatten the cell map
    cell_map = row.pop("c {.*}", None) or {}
    return {**cell_map, **row}


def get_cell_basic(client: Neo4jClient, cell_id: str) -> dict | None:
    rows = client.run(
        "MATCH (c:Cell {id: $id}) RETURN c.id AS id, c.label AS label, c.value AS value, c.formula_raw AS formula, c.sheet AS sheet",
        id=cell_id,
    )
    return rows[0] if rows else None


def get_cell_autocomplete(client: Neo4jClient, prefix: str, limit: int = 20) -> list[dict]:
    if not prefix:
        return []
    return client.run(
        """
        MATCH (c:Cell)
        WHERE c.id CONTAINS $prefix OR c.label CONTAINS $prefix
        RETURN c.id AS id, c.label AS label, c.sheet AS sheet
        LIMIT $limit
        """,
        prefix=prefix,
        limit=limit,
    )


def get_cells_by_ids(client: Neo4jClient, ids: list[str]) -> list[dict]:
    if not ids:
        return []
    return client.run(
        "MATCH (c:Cell) WHERE c.id IN $ids RETURN c.id AS id, c.label AS label, c.value AS value, c.formula_raw AS formula, c.sheet AS sheet",
        ids=ids,
    )


def get_cell_upstream(client: Neo4jClient, cell_id: str, limit: int = 50) -> list[dict]:
    return client.run(
        """
        MATCH (c:Cell {id: $id})-[:DEPENDS_ON]->(dep:Cell)
        RETURN dep.id AS id, dep.label AS label, dep.value AS value, dep.sheet AS sheet
        LIMIT $limit
        """,
        id=cell_id,
        limit=limit,
    )


def get_cell_downstream(client: Neo4jClient, cell_id: str, limit: int = 50) -> list[dict]:
    return client.run(
        """
        MATCH (dep:Cell)-[:DEPENDS_ON]->(c:Cell {id: $id})
        RETURN dep.id AS id, dep.label AS label, dep.value AS value, dep.sheet AS sheet
        LIMIT $limit
        """,
        id=cell_id,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Dependency analysis
# ---------------------------------------------------------------------------

def get_sheet_dependency_matrix(client: Neo4jClient) -> dict[tuple[str, str], int]:
    rows = client.run(
        """
        MATCH (src:Cell)-[:DEPENDS_ON]->(tgt:Cell)
        WHERE src.sheet <> tgt.sheet
        RETURN src.sheet AS src_sheet, tgt.sheet AS tgt_sheet, count(*) AS cnt
        """
    )
    return {(r["src_sheet"], r["tgt_sheet"]): r["cnt"] for r in rows}


def get_top_depended_cells(client: Neo4jClient, limit: int = 20) -> list[dict]:
    return client.run(
        """
        MATCH (dep:Cell)-[:DEPENDS_ON]->(c:Cell)
        RETURN c.id AS id, c.label AS label, c.sheet AS sheet,
               c.value AS value, count(dep) AS downstream_count
        ORDER BY downstream_count DESC
        LIMIT $limit
        """,
        limit=limit,
    )


def get_section_category_distribution(client: Neo4jClient) -> list[dict]:
    return client.run(
        """
        MATCH (sec:Section)
        WHERE sec.category IS NOT NULL AND sec.category <> ''
        RETURN sec.category AS category, count(*) AS count
        ORDER BY count DESC
        """
    )


def get_cross_sheet_edges(client: Neo4jClient) -> list[dict]:
    return client.run(
        """
        MATCH (src:Cell)-[:DEPENDS_ON]->(tgt:Cell)
        WHERE src.sheet <> tgt.sheet
        RETURN src.sheet AS src_sheet, tgt.sheet AS tgt_sheet, count(*) AS weight
        """
    )

"""Bulk-import nodes.json + edges.json into Neo4j."""
import json
from typing import Any

from .neo4j_client import Neo4jClient

_BATCH = 500  # rows per UNWIND batch


def _chunks(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def import_from_json(nodes_path: str, edges_path: str,
                     client: Neo4jClient) -> dict[str, int]:
    """Import graph data from JSON files. Returns counts of created nodes/rels."""
    with open(nodes_path, encoding="utf-8") as f:
        nodes_data = json.load(f)
    with open(edges_path, encoding="utf-8") as f:
        edges_data = json.load(f)

    client.create_constraints()

    wb = nodes_data["workbook"]
    workbook_id = wb["id"]

    # Clear existing data for this workbook
    client.clear_workbook(workbook_id)

    # 1. Workbook node
    client.run_write(
        "MERGE (w:Workbook {id: $id}) SET w += $props",
        id=wb["id"],
        props={k: v for k, v in wb.items() if k != "id"},
    )

    # 2. Sheet + Section nodes
    for sheet in nodes_data["sheets"]:
        client.run_write(
            """
            MERGE (s:Sheet {id: $id})
            SET s += $props
            WITH s
            MATCH (w:Workbook {id: $wid})
            MERGE (w)-[:HAS_SHEET]->(s)
            """,
            id=sheet["id"],
            props={k: v for k, v in sheet.items() if k not in ("id", "sections")},
            wid=workbook_id,
        )
        for sec in sheet.get("sections", []):
            client.run_write(
                """
                MERGE (sec:Section {id: $id})
                SET sec += $props
                WITH sec
                MATCH (s:Sheet {id: $sid})
                MERGE (s)-[:HAS_SECTION]->(sec)
                """,
                id=sec["id"],
                props={k: v for k, v in sec.items() if k != "id"},
                sid=sheet["id"],
            )

    # 3. Cell nodes (batched)
    cells = nodes_data["cells"]
    cell_count = 0
    for batch in _chunks(cells, _BATCH):
        client.run_write(
            """
            UNWIND $rows AS row
            MERGE (c:Cell {id: row.id})
            SET c += row
            """,
            rows=batch,
        )
        cell_count += len(batch)

    # 4. Cell → Section relationships (batched)
    cells_with_section = [c for c in cells if c.get("section")]
    for batch in _chunks(cells_with_section, _BATCH):
        client.run_write(
            """
            UNWIND $rows AS row
            MATCH (c:Cell {id: row.id})
            MATCH (sec:Section {id: row.section})
            MERGE (sec)-[:CONTAINS_CELL]->(c)
            """,
            rows=[{"id": c["id"], "section": c["section"]} for c in batch],
        )

    # 5. DEPENDS_ON relationships (batched)
    deps = edges_data["dependencies"]
    dep_count = 0
    for batch in _chunks(deps, _BATCH):
        client.run_write(
            """
            UNWIND $rows AS row
            MATCH (src:Cell {id: row.source})
            MATCH (tgt:Cell {id: row.target})
            MERGE (src)-[:DEPENDS_ON]->(tgt)
            """,
            rows=batch,
        )
        dep_count += len(batch)

    return {
        "workbook": 1,
        "sheets": len(nodes_data["sheets"]),
        "sections": sum(len(s.get("sections", [])) for s in nodes_data["sheets"]),
        "cells": cell_count,
        "dependencies": dep_count,
    }

import json
import os
import datetime
from dataclasses import asdict
from typing import Any

from parser.schema import WorkbookNode, CellNode


def _serialize(obj: Any) -> Any:
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    return str(obj)


def export_json(workbook: WorkbookNode, output_dir: str) -> tuple[str, str]:
    """Export workbook graph to nodes.json and edges.json.

    Returns (nodes_path, edges_path).
    """
    os.makedirs(output_dir, exist_ok=True)

    all_cells: list[CellNode] = []
    for sheet in workbook.sheets:
        cells = getattr(sheet, "_cells", [])
        all_cells.extend(cells)

    # Build nodes.json
    nodes_payload = {
        "workbook": {
            "id": workbook.id,
            "filename": workbook.filename,
            "upload_time": workbook.upload_time,
            "sheet_count": workbook.sheet_count,
        },
        "sheets": [
            {
                "id": s.id,
                "index": s.index,
                "row_count": s.row_count,
                "col_count": s.col_count,
                "sections": [
                    {
                        "id": sec.id,
                        "name": sec.name,
                        "row_start": sec.row_start,
                        "row_end": sec.row_end,
                        "category": sec.category,
                    }
                    for sec in s.sections
                ],
            }
            for s in workbook.sheets
        ],
        "cells": [
            {
                "id": c.id,
                "sheet": c.sheet,
                "section": c.section_id,
                "row": c.row,
                "col": c.col,
                "value": _serialize(c.value) if isinstance(c.value, (datetime.datetime, datetime.date)) else c.value,
                "value_type": c.value_type,
                "formula_raw": c.formula_raw,
                "is_head": c.is_head,
                "row_category": c.row_category,
                "col_category": c.col_category,
                "unit": c.unit,
                "label": c.label,
                "description": c.description,
            }
            for c in all_cells
        ],
    }

    # Build edges.json
    dependencies = []
    for c in all_cells:
        for ref in c.formula_refs:
            dependencies.append({
                "source": c.id,
                "target": ref,
                "type": "DEPENDS_ON",
                "formula": c.formula_raw,
            })

    edges_payload = {"dependencies": dependencies}

    nodes_path = os.path.join(output_dir, "nodes.json")
    edges_path = os.path.join(output_dir, "edges.json")

    with open(nodes_path, "w", encoding="utf-8") as f:
        json.dump(nodes_payload, f, ensure_ascii=False, indent=2)

    with open(edges_path, "w", encoding="utf-8") as f:
        json.dump(edges_payload, f, ensure_ascii=False, indent=2)

    return nodes_path, edges_path

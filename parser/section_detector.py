from typing import Optional, TYPE_CHECKING
from .schema import SectionNode

if TYPE_CHECKING:
    from llm.base import LLMProvider


def detect_sections(sheet_name: str, rows_data: list[dict],
                    merged_ranges: list[tuple],
                    llm_provider: Optional["LLMProvider"] = None,
                    sheet_meta: Optional[dict] = None) -> list[SectionNode]:
    """Detect logical sections within a sheet.

    When llm_provider is given, uses LLM for structure recognition and falls
    back to rule-based detection if the LLM call fails.

    rows_data: list of dicts keyed by col letter, value is cell value.
               Each dict also has '_row' (int) and '_is_head' (bool).
    merged_ranges: list of (min_row, min_col_idx, max_row, max_col_idx) tuples.
    sheet_meta: extra info passed to LLM (max_row, max_col, etc.)
    """
    if llm_provider is not None:
        try:
            return _detect_with_llm(sheet_name, rows_data, merged_ranges,
                                    llm_provider, sheet_meta or {})
        except Exception:
            pass  # fall through to rule-based

    return _detect_rule_based(sheet_name, rows_data, merged_ranges)


# ---------------------------------------------------------------------------
# Rule-based detection (original logic)
# ---------------------------------------------------------------------------

def _detect_rule_based(sheet_name: str, rows_data: list[dict],
                       merged_ranges: list[tuple]) -> list[SectionNode]:
    """Rule-based: B-column category values define section boundaries."""
    sections: list[SectionNode] = []
    current_name: Optional[str] = None
    current_start: Optional[int] = None

    def close_section(end_row: int) -> None:
        nonlocal current_name, current_start
        if current_name and current_start is not None:
            sec_id = f"{sheet_name}_{current_name}"
            sections.append(SectionNode(
                id=sec_id,
                sheet_id=sheet_name,
                name=current_name,
                row_start=current_start,
                row_end=end_row,
            ))
        current_name = None
        current_start = None

    for row_dict in rows_data:
        row_num = row_dict.get("_row", 0)
        is_head = row_dict.get("_is_head", False)
        b_val = row_dict.get("B")

        if is_head:
            continue

        if b_val and isinstance(b_val, str) and b_val.strip():
            if current_name and current_name != b_val.strip():
                close_section(row_num - 1)
            if current_name != b_val.strip():
                current_name = b_val.strip()
                current_start = row_num

    if rows_data:
        close_section(rows_data[-1].get("_row", 0))

    return sections


# ---------------------------------------------------------------------------
# LLM-enhanced detection
# ---------------------------------------------------------------------------

def _build_sheet_sample(sheet_name: str, rows_data: list[dict],
                        merged_ranges: list[tuple],
                        sheet_meta: dict) -> dict:
    """Build the sheet_sample dict expected by LLMProvider.analyze_sheet_structure."""
    # Find header row: first row with _is_head=True
    headers: dict[str, str] = {}
    for row in rows_data:
        if row.get("_is_head"):
            for k, v in row.items():
                if not k.startswith("_") and v is not None:
                    headers[k] = str(v)
            break

    # Sample: first 30 non-header, non-empty rows
    sample_rows = [
        r for r in rows_data
        if not r.get("_is_head") and any(
            v is not None for k, v in r.items() if not k.startswith("_")
        )
    ][:30]

    merged_strs = [
        f"{chr(64 + (min_c or 1))}{min_r or 1}:{chr(64 + (max_c or 1))}{max_r or 1}"
        for (min_r, min_c, max_r, max_c) in merged_ranges
        if min_r and min_c and max_r and max_c  # skip invalid ranges
    ]

    return {
        "sheet_name": sheet_name,
        "max_row": sheet_meta.get("max_row", len(rows_data)),
        "max_col": sheet_meta.get("max_col", 12),
        "headers": headers,
        "sample_rows": sample_rows,
        "merged_ranges": merged_strs,
    }


def _detect_with_llm(sheet_name: str, rows_data: list[dict],
                     merged_ranges: list[tuple],
                     llm_provider: "LLMProvider",
                     sheet_meta: dict) -> list[SectionNode]:
    """Use LLM to identify sections, then enrich with business categories."""
    sample = _build_sheet_sample(sheet_name, rows_data, merged_ranges, sheet_meta)
    structure = llm_provider.analyze_sheet_structure(sample)

    sections: list[SectionNode] = []
    for sec_info in structure.sections:
        # Deduplicate section id if name repeats
        sec_id = f"{sheet_name}_{sec_info.name}"
        existing_ids = {s.id for s in sections}
        if sec_id in existing_ids:
            sec_id = f"{sec_id}_{sec_info.row_start}"

        sections.append(SectionNode(
            id=sec_id,
            sheet_id=sheet_name,
            name=sec_info.name,
            row_start=sec_info.row_start,
            row_end=sec_info.row_end,
            category=sec_info.category,
        ))

    return sections


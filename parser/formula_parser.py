import re
from typing import Optional


# Regex patterns for extracting cell references from Excel formulas
_CROSS_SHEET_SINGLE = re.compile(r"(?:^|[^'\w])'?([^'!\[\],+\-*/()=<>& ]+)'?!([A-Z]{1,3})(\d+)")
_CROSS_SHEET_RANGE = re.compile(r"(?:^|[^'\w])'?([^'!\[\],+\-*/()=<>& ]+)'?!([A-Z]{1,3})(\d+):([A-Z]{1,3})(\d+)")
_LOCAL_RANGE = re.compile(r"(?<![!'\w])([A-Z]{1,3})(\d+):([A-Z]{1,3})(\d+)")
_LOCAL_SINGLE = re.compile(r"(?<![!'\w])([A-Z]{1,3})(\d+)(?!\d)")


def col_letter_to_index(col: str) -> int:
    """Convert column letter(s) to 0-based index. A=0, Z=25, AA=26."""
    result = 0
    for ch in col.upper():
        result = result * 26 + (ord(ch) - ord('A') + 1)
    return result - 1


def index_to_col_letter(index: int) -> str:
    """Convert 0-based column index to letter(s)."""
    result = ""
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _expand_range(sheet: str, col_start: str, row_start: int,
                  col_end: str, row_end: int) -> list[str]:
    """Expand a cell range into individual cell ids."""
    c_start = col_letter_to_index(col_start)
    c_end = col_letter_to_index(col_end)
    refs = []
    for r in range(row_start, row_end + 1):
        for c in range(c_start, c_end + 1):
            refs.append(f"{sheet}_{r}_{index_to_col_letter(c)}")
    return refs


def parse_formula_refs(formula: str, current_sheet: str) -> list[str]:
    """Extract all cell dependency ids from an Excel formula string.

    Returns a deduplicated list of cell ids in the form "{sheet}_{row}_{col}".

    Examples:
        "=ROUNDUP(I10,0)"          → ["参数输入表_10_I"]
        "=SUM(I14:I23)"            → ["参数输入表_14_I", ..., "参数输入表_23_I"]
        "=投资概算明细!F24"         → ["投资概算明细_24_F"]
        "=时间序列!D5+参数输入表!I5" → ["时间序列_5_D", "参数输入表_5_I"]
    """
    if not formula or not formula.startswith("="):
        return []

    refs: list[str] = []
    seen: set[str] = set()

    def add(cell_id: str) -> None:
        if cell_id not in seen:
            seen.add(cell_id)
            refs.append(cell_id)

    # Strip leading '=' and remove string literals to avoid false matches
    cleaned = re.sub(r'"[^"]*"', '""', formula[1:])

    # 1. Cross-sheet ranges: Sheet!A1:B3
    for m in _CROSS_SHEET_RANGE.finditer(cleaned):
        sheet, c1, r1, c2, r2 = m.group(1), m.group(2), int(m.group(3)), m.group(4), int(m.group(5))
        for cid in _expand_range(sheet, c1, r1, c2, int(r2)):
            add(cid)

    # 2. Cross-sheet singles: Sheet!A1
    for m in _CROSS_SHEET_SINGLE.finditer(cleaned):
        sheet, col, row = m.group(1), m.group(2), int(m.group(3))
        add(f"{sheet}_{row}_{col}")

    # Remove cross-sheet tokens so they don't re-match as local refs
    cleaned_local = _CROSS_SHEET_SINGLE.sub("", _CROSS_SHEET_RANGE.sub("", cleaned))

    # 3. Local ranges: A1:B3
    for m in _LOCAL_RANGE.finditer(cleaned_local):
        c1, r1, c2, r2 = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
        for cid in _expand_range(current_sheet, c1, r1, c2, int(r2)):
            add(cid)

    # Remove range tokens
    cleaned_local = _LOCAL_RANGE.sub("", cleaned_local)

    # 4. Local singles: A1
    for m in _LOCAL_SINGLE.finditer(cleaned_local):
        col, row = m.group(1), int(m.group(2))
        add(f"{current_sheet}_{row}_{col}")

    return refs

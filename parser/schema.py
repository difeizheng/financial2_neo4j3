from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CellNode:
    id: str                          # "{sheet}_{row}_{col}"
    sheet: str
    row: int
    col: str                         # column letter, e.g. "I"
    value: Any                       # computed/stored value
    value_type: str                  # number | string | date | boolean | null
    formula_raw: Optional[str]       # raw Excel formula string, None if no formula
    formula_refs: list[str]          # list of cell ids this cell depends on
    is_head: bool
    row_category: Optional[str]      # category from col B of same row
    col_category: Optional[str]      # header from row 3 of same col
    unit: Optional[str]              # from col J
    label: Optional[str]             # parameter name from col D
    description: Optional[str]       # from col K
    section_id: Optional[str] = None


@dataclass
class SectionNode:
    id: str                          # "{sheet}_{section_name}"
    sheet_id: str
    name: str
    row_start: int
    row_end: int
    category: str = "general"        # input_parameter | financial_statement | etc.


@dataclass
class SheetNode:
    id: str                          # sheet name
    workbook_id: str
    index: int
    row_count: int
    col_count: int
    sections: list[SectionNode] = field(default_factory=list)


@dataclass
class WorkbookNode:
    id: str
    filename: str
    upload_time: str
    sheet_count: int
    sheets: list[SheetNode] = field(default_factory=list)

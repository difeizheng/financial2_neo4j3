"""LLM provider abstraction for sheet structure recognition."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class SectionInfo:
    name: str
    row_start: int
    row_end: int
    category: str = "general"   # input_parameter | financial_statement | time_series | etc.
    description: str = ""


@dataclass
class SheetStructure:
    header_row: int
    sections: list[SectionInfo]
    category_col: Optional[str]   # column letter that holds row categories (e.g. "B")
    value_col: Optional[str]      # primary value column (e.g. "I")
    notes: str = ""


class LLMProvider(ABC):
    """Abstract interface for LLM-powered sheet analysis."""

    @abstractmethod
    def analyze_sheet_structure(self, sheet_sample: dict) -> SheetStructure:
        """Analyze a sheet data sample and return its structural layout.

        sheet_sample keys:
          - sheet_name: str
          - max_row: int
          - max_col: int
          - headers: dict[col_letter, value]  (first non-empty row)
          - sample_rows: list[dict]  (first 30 non-empty rows, each {col: value})
          - merged_ranges: list[str]  (e.g. ["B4:B12", "B13:B32"])
        """

    @abstractmethod
    def classify_section(self, section_name: str, sample_labels: list[str]) -> str:
        """Return a business category for a section.

        Returns one of: input_parameter | financial_statement | time_series |
                        depreciation | cost | revenue | cashflow | balance_sheet | general
        """

    def name(self) -> str:
        return self.__class__.__name__

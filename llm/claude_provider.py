"""Anthropic Claude provider."""
import json

import anthropic

from config import ANTHROPIC_API_KEY
from .base import LLMProvider, SheetStructure, SectionInfo
from .siliconflow_provider import _SYSTEM_PROMPT, _USER_TEMPLATE


class ClaudeProvider(LLMProvider):
    def __init__(self, api_key: str = ANTHROPIC_API_KEY,
                 model: str = "claude-haiku-4-5-20251001"):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def name(self) -> str:
        return f"Claude/{self._model}"

    def analyze_sheet_structure(self, sheet_sample: dict) -> SheetStructure:
        headers_str = "\n".join(
            f"  {col}: {val}" for col, val in sheet_sample.get("headers", {}).items()
        )
        sample_str = "\n".join(
            "  行{}: {}".format(
                row.get("_row", "?"),
                " | ".join(f"{k}={v}" for k, v in row.items() if not k.startswith("_") and v is not None)
            )
            for row in sheet_sample.get("sample_rows", [])
        )
        prompt = _USER_TEMPLATE.format(
            sheet_name=sheet_sample.get("sheet_name", ""),
            max_row=sheet_sample.get("max_row", 0),
            max_col=sheet_sample.get("max_col", 0),
            merged_ranges=", ".join(sheet_sample.get("merged_ranges", [])) or "无",
            headers=headers_str or "（未检测到）",
            sample_rows=sample_str or "（无数据）",
        )
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw.strip())
        sections = [
            SectionInfo(
                name=s["name"], row_start=s["row_start"], row_end=s["row_end"],
                category=s.get("category", "general"), description=s.get("description", ""),
            )
            for s in data.get("sections", [])
        ]
        return SheetStructure(
            header_row=data.get("header_row", 3),
            sections=sections,
            category_col=data.get("category_col"),
            value_col=data.get("value_col"),
            notes=data.get("notes", ""),
        )

    def classify_section(self, section_name: str, sample_labels: list[str]) -> str:
        prompt = (
            f"分区名称：{section_name}\n"
            f"包含的参数标签（前10个）：{', '.join(sample_labels[:10])}\n\n"
            "请从以下类别中选择最合适的一个，只返回类别名称：\n"
            "input_parameter | financial_statement | time_series | depreciation | "
            "cost | revenue | cashflow | balance_sheet | general"
        )
        msg = self._client.messages.create(
            model=self._model, max_tokens=20,
            messages=[{"role": "user", "content": prompt}],
        )
        result = msg.content[0].text.strip().lower()
        valid = {"input_parameter", "financial_statement", "time_series",
                 "depreciation", "cost", "revenue", "cashflow", "balance_sheet", "general"}
        return result if result in valid else "general"

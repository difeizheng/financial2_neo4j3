"""SiliconFlow provider — uses OpenAI-compatible API."""
import json
from typing import Optional

from openai import OpenAI

from config import SILICONFLOW_API_KEY, SILICONFLOW_BASE_URL, SILICONFLOW_MODEL
from .base import LLMProvider, SheetStructure, SectionInfo

_SYSTEM_PROMPT = """你是一个专业的财务模型Excel表格结构分析专家。
用户会给你一个Excel sheet的样本数据，你需要识别：
1. 表头行号（header_row）
2. 表内的逻辑分区（sections），每个分区有名称、起始行、结束行、业务类别
3. 行类别列（category_col）：哪一列存放行的类别标签（如B列）
4. 主数值列（value_col）：哪一列存放主要数值（如I列）

业务类别（category）必须是以下之一：
input_parameter | financial_statement | time_series | depreciation | cost | revenue | cashflow | balance_sheet | general

请严格返回JSON格式，不要有任何额外文字。"""

_USER_TEMPLATE = """Sheet名称：{sheet_name}
行数：{max_row}，列数：{max_col}
合并单元格：{merged_ranges}

列标题（第一个非空行）：
{headers}

前30行样本数据：
{sample_rows}

请分析该sheet的结构，返回如下JSON：
{{
  "header_row": <int>,
  "category_col": "<col_letter或null>",
  "value_col": "<col_letter或null>",
  "sections": [
    {{"name": "<分区名>", "row_start": <int>, "row_end": <int>, "category": "<业务类别>", "description": "<简短说明>"}}
  ],
  "notes": "<其他说明>"
}}"""


class SiliconFlowProvider(LLMProvider):
    def __init__(self, api_key: str = SILICONFLOW_API_KEY,
                 base_url: str = SILICONFLOW_BASE_URL,
                 model: str = SILICONFLOW_MODEL):
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def name(self) -> str:
        return f"SiliconFlow/{self._model}"

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

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=2048,
        )

        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        data = json.loads(raw)
        sections = [
            SectionInfo(
                name=s["name"],
                row_start=s["row_start"],
                row_end=s["row_end"],
                category=s.get("category", "general"),
                description=s.get("description", ""),
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
            "请从以下类别中选择最合适的一个，只返回类别名称，不要其他文字：\n"
            "input_parameter | financial_statement | time_series | depreciation | "
            "cost | revenue | cashflow | balance_sheet | general"
        )
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=20,
        )
        result = response.choices[0].message.content.strip().lower()
        valid = {"input_parameter", "financial_statement", "time_series",
                 "depreciation", "cost", "revenue", "cashflow", "balance_sheet", "general"}
        return result if result in valid else "general"

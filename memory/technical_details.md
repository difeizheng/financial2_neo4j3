---
name: 技术细节
description: 公式解析、计算引擎、变更传播、LLM识别算法
type: reference
---

## 公式解析

支持跨sheet引用：
- `Sheet!A1` → `{sheet}_{row}_{col}` cell_id格式
- `Sheet!A1:B3` → 范围展开为cell列表

## 计算引擎 (CalcEngine)

11个高频Excel函数实现：
- SUM, ROUND, ROUNDUP, ROUNDDOWN
- IF, MAX, MIN, ABS
- DATEDIF, IFERROR, SUMIF

复杂函数（VLOOKUP/INDEX/MATCH）返回None保持原值。

## 变更传播 (Propagator)

拓扑排序算法：
1. BFS找下游依赖
2. 构建子图邻接表
3. Kahn算法拓扑排序
4. CalcEngine按序重算
5. 批量写回Neo4j

## Cell ID格式

`{sheet}_{row}_{col_letter}`
例: `损益表_42_A`

## LLM表结构识别

- SiliconFlow DeepSeek-V3
- 自动识别Section边界和语义标签

## Why: 核心算法是变更传播，依赖拓扑排序和CalcEngine协同。
## How to apply: 理解cell_id格式，CalcEngine返回None表示不可计算，Propagator会跳过。
---
name: 项目概览
description: 财务模型知识图谱系统完整架构和技术栈
type: project
---

# 财务模型知识图谱系统

## 核心功能

Excel财务模型解析为Neo4j知识图谱，支持公式依赖分析、变更传播、LLM智能识别。

## 技术架构

| 层级 | 组件 | 技术 |
|------|------|------|
| 解析层 | Excel解析 | openpyxl + 正则公式解析 |
| 存储层 | 图数据库 | Neo4j 5.x |
| 计算层 | 公式引擎 | 自实现11个高频函数 |
| UI层 | Streamlit | 6页面路由应用 |
| 可视化 | pyvis | 交互式图谱 |
| 智能层 | LLM | SiliconFlow DeepSeek-V3 |

## 目录结构

```
├── app.py          # Streamlit路由入口
├── main.py         # CLI入口
├── config.py       # 配置管理
├── engine/         # 计算引擎
│   └── calc_engine.py  # 11个Excel函数实现
├── graph/          # Neo4j图谱
│   ├── neo4j_client.py
│   ├── importer.py      # 导入逻辑
│   ├── propagator.py    # 变更传播（拓扑排序）
│   └── queries.py       # 查询封装
├── parser/         # 公式解析
├── llm/            # LLM集成（多provider）
├── pages/          # Streamlit页面
│   ├── upload.py    # 上传解析
│   ├── tasks.py     # 任务列表
│   ├── dashboard.py # 仪表盘
│   ├── browser.py   # 数据浏览
│   ├── graph_view.py # 图谱可视化
│   └── simulation.py # 变更模拟
├── viz/            # 可视化模块
├── task_manager/   # SQLite任务管理
└── data/           # 数据目录
```

## 测试数据规模

- 14个sheet
- 58,482个cell
- 42,942个公式
- 129,031条依赖关系
- 785个业务分区

## Why: 将复杂Excel财务模型转化为可查询、可分析的知识图谱，解决公式依赖追踪和变更影响分析痛点。
## How to apply: 理解三层语义模型（Sheet→Section→Cell），变更传播使用拓扑排序+CalcEngine。
# 财务模型知识图谱系统

将复杂Excel财务模型解析为Neo4j知识图谱，支持公式依赖分析、变更传播、LLM智能识别。

## 功能特性

- **Excel解析** — openpyxl + 正则公式解析，支持跨sheet引用
- **Neo4j图谱** — 三层语义模型（Sheet→Section→Cell）
- **变更传播** — 拓扑排序 + 11个Excel函数计算引擎
- **Streamlit UI** — 4页面应用，pyvis交互式可视化
- **LLM智能识别** — SiliconFlow DeepSeek-V3表结构自动识别

## 快速启动

```bash
# CLI模式
pip install -r requirements.txt
python main.py "excel.xlsx" --llm --neo4j

# Streamlit UI
streamlit run app.py
```

## 技术栈

| 组件 | 技术 |
|------|------|
| Excel解析 | openpyxl |
| 图数据库 | Neo4j 5.x |
| UI框架 | Streamlit |
| 可视化 | pyvis |
| LLM | SiliconFlow DeepSeek-V3 |

## 测试数据

- 14个sheet，58,482个cell，42,942个公式
- 129,031条依赖关系，785个业务分区

## 待办事项 (v2.0.0)

- [ ] D3.js高性能可视化 — 支持58K节点大规模图谱
- [ ] 更多Excel函数 — VLOOKUP/INDEX/MATCH/SUMIFS
- [ ] 批量上传和并行解析 — 多Excel同时处理
- [ ] 变更历史和审计日志 — 操作记录
- [ ] 导出功能 — Cypher/GraphML/CSV
- [ ] 多用户权限管理 — 用户隔离

## License

MIT
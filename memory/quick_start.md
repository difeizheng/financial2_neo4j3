---
name: 快速启动
description: CLI/Streamlit启动、常见操作、故障排查
type: reference
---

## 启动方式

### CLI模式
```bash
pip install -r requirements.txt
python main.py "excel.xlsx" --llm --neo4j
```

### Streamlit UI
```bash
streamlit run app.py
```

## 环境配置 (.env)

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
LLM_PROVIDER=siliconflow
SILICONFLOW_API_KEY=xxx
```

## Neo4j连接检查

```python
from graph.neo4j_client import Neo4jClient
client = Neo4jClient()
client.verify_connectivity()  # 返回True/False
```

## 常见问题

| 问题 | 解决 |
|------|------|
| Neo4j连接失败 | 检查端口7687、密码配置 |
| LLM调用失败 | 检查API_KEY、provider配置 |
| 公式计算错误 | CalcEngine不支持该函数 |
| 图谱不显示 | pyvis依赖、浏览器兼容 |

## Why: 快速启动指南帮助恢复工作流。
## How to apply: 启动前检查.env配置，Neo4j和LLM服务状态。
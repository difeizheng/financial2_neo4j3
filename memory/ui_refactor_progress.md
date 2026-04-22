---
name: UI重构进度
description: Streamlit UI重构当前状态、已创建/未完成文件
type: project
---

## UI重构状态

已完成6页面框架：
- ✅ app.py（路由入口）
- ✅ pages/__init__.py（session_state初始化）
- ✅ pages/upload.py（上传解析）
- ✅ pages/tasks.py（任务列表）
- ✅ pages/dashboard.py（仪表盘统计）
- ✅ pages/browser.py（数据浏览+搜索）
- ✅ pages/graph_view.py（pyvis图谱可视化）
- ✅ pages/simulation.py（变更模拟+dry_run）

## 导航路由

PAGES字典映射：
```
📤 上传解析 → upload
📋 任务列表 → tasks
📊 仪表盘 → dashboard
🔍 数据浏览 → browser
🕸️ 图谱浏览 → graph_view
🔄 变更模拟 → simulation
```

## 侧边栏

- 工作簿选择器（Neo4j Workbook节点）
- 连接状态提示

## 待优化

- [ ] D3.js高性能可视化（58K节点）
- [ ] 更多Excel函数支持
- [ ] 批量上传并行解析
- [ ] 导出功能（Cypher/GraphML/CSV）

## Why: UI框架完成，功能可用，待性能优化。
## How to apply: 新功能开发优先现有页面扩展，避免重写框架。
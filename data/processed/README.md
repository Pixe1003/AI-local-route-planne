# Processed Data

半生产版 RAG 默认读取 `data/processed/hefei_pois.sqlite`，其中 `app_pois` 视图提供合肥 POI 属性、商圈、标签和高频关键词。该 SQLite 文件体积较大，不提交到仓库。

构建本地向量索引：

```powershell
$env:PYTHONPATH='backend'
python -m app.repositories.rag_index build --city hefei --source data/processed/hefei_pois.sqlite --reset
```

如果 SQLite、embedding API 或 Chroma 索引不可用，后端会降级到内置 seed 数据和规则评分链路。

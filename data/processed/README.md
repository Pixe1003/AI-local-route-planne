# Processed Data

半生产版 RAG 默认读取 `data/processed/hefei_pois.sqlite`，其中 `app_pois` 提供合肥 POI 属性、商圈、标签和高频关键词，`poi_feature_index` 提供类目与召回特征，`ugc_evidence_index` 提供评论证据。该 SQLite 文件体积较大，不提交到仓库，可由仓库内 JSONL 重建。

重建 POI SQLite：

```powershell
$env:AMAP_KEY='<高德 Web 服务 key>' # 可选；没有 key 时非餐饮 POI 使用区级估算坐标兜底
python scripts/build_poi_sqlite.py --city hefei --source data/processed/ugc_hefei.jsonl --out data/processed/hefei_pois.sqlite --geocode-cache data/processed/amap_geocode_cache.json --reset
```

构建本地向量索引：

```powershell
$env:PYTHONPATH='backend'
python -m app.repositories.rag_index build --city hefei --source data/processed/hefei_pois.sqlite --reset
```

如果 SQLite、embedding API 或 Chroma 索引不可用，后端会降级到内置 seed 数据和规则评分链路。

# AIroute 成品冲刺开发计划

## 当前决策

- 后续开发以已合并 PR #6 的 `main+FAISS` 为基线，不再回到旧 Chroma 分支。
- 当前阶段优先交付“真实合肥数据 + FAISS RAG + 出发点就近 + 高德距离/耗时 + 前端证据展示”。
- LLM 真模型、LLM-as-judge、insertion/2-opt、partial replan completed stops、CI quality gates wiring 后置。

## 已完成到本分支

- `/health` 暴露 rag/faiss/amap/memory/cache 的 `status`，可区分 ready/degraded。
- `scripts/build_faiss_rag.py` 支持 `--sqlite-path`、`--require-real-data`、`--limit`，避免缺真实 DB 时误用 seed 当成真 RAG。
- 后端 pool 支持 `origin_latitude`、`origin_longitude`、`radius_meters`，输出 `distance_meters`，并对半径外 POI 做过滤。
- Agent run 请求和 tool 层透传 origin/radius。
- `estimate_transport` 优先调用高德，失败或无 key 时降级 haversine，并标记 `Transport.source`。
- 前端生成请求默认带合肥中心坐标和半径；路线页展示 distance、retrieval provenance、UGC evidence 和 data warning。

## Demo 前检查

```powershell
$env:PYTHONPATH='backend'
$env:AIROUTE_REAL_DATA_DIR='D:\Users\12057\Desktop\美团黑客松\AIroute\data\processed'
python -m pytest backend/tests/test_product_demo_readiness.py::test_real_hefei_data_smoke_when_configured backend/tests/test_product_demo_readiness.py::test_real_hefei_faiss_smoke_when_configured -q

python scripts/build_faiss_rag.py --city hefei --sqlite-path "$env:AIROUTE_REAL_DATA_DIR\hefei_pois.sqlite" --require-real-data --index-dir data/faiss
curl http://127.0.0.1:8000/health
```

验收时 `/health` 里 `rag.status` 应为 `ready`，`faiss.document_count` 应大于 0，前端路线页应能看到 `semantic_*` 和真实 UGC evidence。

## 下一阶段

- 将 `estimate_transport` 的高德调用批量化或缓存化，减少 solver 多段路线时的客户端创建成本。
- 做 insertion + 2-opt 局部搜索替换 greedy。
- partial replan 增加已完成站点和当前位置概念。
- 打通 LLM 真模型解释，并保持无 key 规则降级。
- 把 quality gates、真实数据 smoke、容器启动纳入 CI 或发布前脚本。

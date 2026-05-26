# Backend

FastAPI 后端按 `api -> services -> repositories/solver/llm` 分层。默认城市为合肥（hefei），POI 数据来自 `data/processed/hefei_pois.sqlite`（三表结构）加内置 seed 兜底；DeepSeek/兼容 LLM、嵌入服务、高德不可用时也能完成 Demo 主链路（自动降级为本地评分与 haversine 距离估算）。

`GET /api/meta/integrations` 可查看 LLM、Embedding、高德和 RAG 索引是否启用。行程与版本历史持久化在 `APP_STATE_SQLITE_PATH`（默认 `./data/processed/app_state.sqlite`）。

```bash
python -m pip install -e .[dev]
python -m pytest tests -q
python -m uvicorn app.main:app --reload --port 8000
```

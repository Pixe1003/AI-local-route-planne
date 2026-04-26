# Backend

FastAPI 后端按 `api -> services -> repositories/solver/llm` 分层。默认使用内置上海 POI seed 数据，外部数据库、DeepSeek、高德不可用时也能完成 Demo 主链路。

```bash
python -m pip install -e .[dev]
python -m pytest tests -q
python -m uvicorn app.main:app --reload --port 8000
```

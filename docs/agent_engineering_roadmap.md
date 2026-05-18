# AIroute 工程化拓展开发指导（聚焦版）

> 在三层记忆系统已闭环的基础上，把项目从"功能完整"推到"工程可观测、可缓存、可评估"的下一阶段。
>
> 本文档聚焦四个最关键的工程方向：扫尾遗留问题、可观测性、缓存策略（含 Redis 适用性分析）、质量工程。
>
> 总工时约 4-5 天。

---

## 一、扫尾遗留小问题（半天）

来自上一轮记忆功能评估的 6 个不阻塞但需要修的问题。

### 1.1 `recall_similar_sessions` 在规则路径下接通

当前 Conductor 的 `_rule_based_decision` 序列没有 `recall_similar_sessions`，工具仅在 LLM tool calling 模式下可达，规则模式是死代码。

修复：

```python
# app/agent/conductor.py 修改 _rule_based_decision 第 113 行附近
if state.memory.intent is None:
    return Decision(tool="parse_intent", args={"free_text": state.goal.raw_query})

# 新增：有历史则先做 vector recall
if (state.memory.episodic_summary
    and not state.memory.similar_sessions_searched):
    return Decision(
        tool="recall_similar_sessions",
        args={"query": state.goal.raw_query, "top_k": 3},
    )

if not state.memory.ugc_searched:
    return Decision(tool="search_ugc_evidence", ...)
```

`build_initial_state._load_similar_sessions` 已经预载一次（设 `similar_sessions_searched=True`），所以新规则只在首次冷启动用户或预载失败时触发，不会重复 BGE 推理。如果想让 trace 里始终能看到这个工具被调用以便 demo，加一个开关：

```python
# app/config.py
prefer_tool_recall_in_trace: bool = False  # 设 True 时 build_initial_state 跳过预载，让工具走

# routes_agent.py _enrich_initial_memory
if not get_settings().prefer_tool_recall_in_trace:
    state.memory.similar_sessions = _load_similar_sessions(request, session_id)
    state.memory.similar_sessions_searched = True
```

### 1.2 `typical_time_windows` 接入

`UserFacts.typical_time_windows` 派生了但没有消费方。让 `UserNeedProfile.to_plan_context` 在用户没填 time_window 时用 facts 兜底：

```python
# app/agent/user_memory.py 新增反向映射
TIME_WINDOW_MAP = {
    "weekday_morning": ("08:00", "12:00"),
    "weekday_afternoon": ("13:00", "17:00"),
    "weekday_evening": ("18:00", "22:00"),
    "weekend_morning": ("09:00", "13:00"),
    "weekend_afternoon": ("13:00", "18:00"),
    "weekend_evening": ("18:00", "23:00"),
}

def bucket_to_time_window(bucket: str | None) -> tuple[str, str] | None:
    return TIME_WINDOW_MAP.get(bucket or "")
```

```python
# app/api/routes_agent.py _enrich_initial_memory 内追加
if request.time_window is None and state.memory.user_facts:
    from app.agent.user_memory import bucket_to_time_window
    bucket = (state.memory.user_facts.typical_time_windows or [None])[0]
    inferred = bucket_to_time_window(bucket)
    if inferred:
        state.context.time_window = TimeWindow(start=inferred[0], end=inferred[1])
```

### 1.3 `_district_from_address` 改读结构化字段

当前 `_district_from_address` 第 117-123 行硬编码 6 个合肥区域，换城市数据就 mismatch。改成从 `PoiDetail.district` 读结构化字段。

`PoiDetail` 加字段：

```python
# app/schemas/poi.py
class PoiDetail(BaseModel):
    # ... 已有字段
    district: str | None = None
```

`PoiRepository._row_to_poi` 已经有 `district = row["district"]` 局部变量，直接挂到模型：

```python
# app/repositories/poi_repo.py 第 50 行附近
return PoiDetail(
    # ... 已有字段
    district=district,
)
```

`user_memory._favorite_districts` 简化：

```python
def _favorite_districts(summaries) -> list[str]:
    repo = get_poi_repository()
    districts: Counter[str] = Counter()
    for summary in summaries:
        for poi_id in summary.stop_poi_ids:
            try:
                poi = repo.get(poi_id)
            except KeyError:
                continue
            if poi.district:
                districts[poi.district] += 1
    return [d for d, _ in districts.most_common(3)]
```

删除 `_district_from_address` 函数。

### 1.4 `data/processed/sessions/` 暖启动脚本

clone 仓库后 sessions 目录为空，demo 时 user_facts 和 similar_sessions 都是空——影响演示效果。加一个一次性 warmup 脚本：

```python
# scripts/warmup_demo_sessions.py
"""一次性灌入 3-5 个 demo session，让记忆系统立刻有内容展示。"""
import httpx
import time

DEMO_QUERIES = [
    {"user_id": "demo_user", "free_text": "想吃合肥本地菜，少排队", "budget_per_person": 150},
    {"user_id": "demo_user", "free_text": "和朋友吃火锅，预算高一点", "budget_per_person": 250},
    {"user_id": "demo_user", "free_text": "下午找个安静咖啡", "budget_per_person": 80},
    {"user_id": "demo_user", "free_text": "想再试试本地特色", "budget_per_person": 180},
]


def main():
    base = "http://localhost:8000"
    for index, query in enumerate(DEMO_QUERIES, start=1):
        print(f"[{index}/{len(DEMO_QUERIES)}] {query['free_text']}")
        response = httpx.post(
            f"{base}/api/agent/run",
            json={
                **query,
                "city": "hefei",
                "date": "2026-05-08",
                "time_window": {"start": "14:00", "end": "20:00"},
            },
            timeout=60,
        )
        response.raise_for_status()
        time.sleep(1)
    facts = httpx.get(f"{base}/api/agent/user/demo_user/facts?force_refresh=true").json()
    print(f"\nWarmed up. Facts: session_count={facts['session_count']}, "
          f"favorite_categories={facts['favorite_categories']}")


if __name__ == "__main__":
    main()
```

README 加一行：`python scripts/warmup_demo_sessions.py`。

### 1.5 FAISS 并发写锁

`SessionVectorRepo._persist` 无锁。daemon thread 从 `save_state` 启动；同一 user 极短时间内连续 save 两次（譬如 adjust + 新 run 几乎同时）可能写文件冲突。加 per-user lock：

```python
# app/repositories/session_vector_repo.py
import threading

class SessionVectorRepo:
    def __init__(self, sessions_dir: str | Path | None = None) -> None:
        # ... 已有
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _user_lock(self, user_id: str) -> threading.Lock:
        with self._locks_guard:
            if user_id not in self._locks:
                self._locks[user_id] = threading.Lock()
            return self._locks[user_id]

    def add_session(self, state, summary):
        with self._user_lock(state.goal.user_id):
            # ... 已有 add_session 全部逻辑
```

`_persist` 内部不需要锁（外层已包）。

### 1.6 `invalidate_facts` 优化

当前 `invalidate_facts` 既清内存 cache 又 DELETE SQLite 行（第 35-37 行），下次 `get_user_facts` 必然走 derive。改成只清内存让 TTL 决策：

```python
# app/agent/user_memory.py
def invalidate_facts(user_id: str) -> None:
    _CACHE.pop(user_id, None)
    # 不删 SQLite，下次读时按 TTL 判断
```

担心数据陈旧的话把 `CACHE_TTL` 调小到 1 分钟。同时把 `save_state` 后的 `_invalidate_user_facts` 调用保留——内存 cache 立刻失效，下次 read 走 SQLite TTL 检查，多数情况下能复用上次写盘的 facts，省一次 derive。

### 扫尾验收

```bash
pytest tests/test_user_facts.py -v         # 验证 facts cache 行为没破
pytest tests/test_episodic_memory.py -v    # 验证 district 抽取改造
pytest tests/test_agent_memory_e2e.py -v   # 三层联动仍通
make warmup                                # warmup 脚本能跑（如果加了 Makefile）
```

---

## 二、可观测性（1 天）

当前观测能力只有 `_EVENTS` dict + SSE 推送。加结构化日志 + 指标 + 成本追踪，让生产排错和性能监控有抓手。

### 2.1 结构化日志（structlog）

```bash
pip install structlog
```

```python
# app/observability/logging.py
import logging
import sys
import structlog


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None):
    return structlog.get_logger(name)
```

`app/main.py` startup：

```python
from app.observability.logging import configure_logging

configure_logging(level=get_settings().log_level)
```

Conductor 接入：

```python
# app/agent/conductor.py
from structlog.contextvars import bind_contextvars, clear_contextvars
from app.observability.logging import get_logger

logger = get_logger(__name__)


class Conductor:
    def run(self, state: AgentState) -> AgentState:
        bind_contextvars(
            session_id=state.goal.session_id,
            trace_id=state.trace_id,
            user_id=state.goal.user_id,
            goal_kind=state.goal.kind,
        )
        logger.info("agent.run.started", phase=state.phase)
        try:
            for _ in range(self.MAX_STEPS):
                decision = self._decide(state)
                logger.info("agent.tool.decided", tool=decision.tool, phase=state.phase)
                # ... 已有
        finally:
            clear_contextvars()
```

每条日志自带 session_id / trace_id / user_id，ELK / Loki / Datadog 都能 query。

### 2.2 Prometheus 指标

```bash
pip install prometheus-client prometheus-fastapi-instrumentator
```

```python
# app/observability/metrics.py
from prometheus_client import Counter, Histogram


TOOL_LATENCY = Histogram(
    "agent_tool_latency_seconds",
    "Tool execution latency in seconds",
    labelnames=["tool_name", "status"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10, 30),
)

AGENT_RUN_LATENCY = Histogram(
    "agent_run_latency_seconds",
    "Full agent run latency",
    labelnames=["goal_kind", "phase"],
    buckets=(0.5, 1, 2, 5, 10, 30),
)

LLM_TOKENS = Counter(
    "agent_llm_tokens_total",
    "Total LLM tokens consumed",
    labelnames=["provider", "model", "kind"],   # kind=input|output|total
)

AMAP_REQUESTS = Counter(
    "agent_amap_requests_total",
    "Amap route requests",
    labelnames=["mode", "status", "cache"],     # cache=hit|miss
)

HALLUCINATION_DETECTED = Counter(
    "agent_hallucination_detected_total",
    "Hallucinated outputs blocked by post_check",
    labelnames=["specialist", "issue"],
)

CACHE_HIT_RATE = Counter(
    "agent_cache_hits_total",
    "Cache hit / miss counts",
    labelnames=["cache_name", "result"],         # result=hit|miss
)

MEMORY_LAYER_USAGE = Counter(
    "agent_memory_layer_usage_total",
    "How often each memory layer contributed to a decision",
    labelnames=["layer"],                         # episodic|semantic|vector
)
```

```python
# app/main.py
from prometheus_fastapi_instrumentator import Instrumentator

# 启用 HTTP 自带指标 + 自定义指标
Instrumentator(should_group_status_codes=False).instrument(app).expose(app, endpoint="/metrics")
```

Conductor 第 40-43 行后写一次：

```python
from app.observability.metrics import TOOL_LATENCY

TOOL_LATENCY.labels(tool_name=decision.tool, status="ok").observe(
    (ended - started).total_seconds()
)
```

异常路径写 `status="error"`。

StoryAgent post_check 失败时：

```python
from app.observability.metrics import HALLUCINATION_DETECTED

for issue in issues:
    HALLUCINATION_DETECTED.labels(specialist="story", issue=issue).inc()
```

LlmClient `complete_tool_call` / `complete_json` 拿到 response 后从 `response.json()["usage"]` 抽 token 计数：

```python
usage = response.json().get("usage", {})
LLM_TOKENS.labels(provider=settings.llm_provider, model=settings.llm_model, kind="input").inc(
    usage.get("prompt_tokens", 0)
)
LLM_TOKENS.labels(provider=settings.llm_provider, model=settings.llm_model, kind="output").inc(
    usage.get("completion_tokens", 0)
)
```

Grafana 接 Prometheus 后能画出：

- agent run 端到端延迟 p50 / p95 / p99
- 每个 tool 的延迟分布与错误率
- 幻觉拦截率（按 specialist + issue 维度）
- token 消耗趋势（按 provider + model）
- 记忆三层各自的命中率

### 2.3 成本追踪

`ToolCall.tokens_used` 字段早就有但没写。补上：

```python
# app/llm/client.py complete_tool_call 末尾
try:
    response.raise_for_status()
    message = response.json()["choices"][0]["message"]
    usage = response.json().get("usage", {})
    # ... 抽 tool_calls
    return {
        "tool": tool_name,
        "args": args,
        "_tokens_used": usage.get("total_tokens", 0),
    }
except Exception:
    return fallback
```

Conductor 解析 `_tokens_used` 写进 `ToolCall.tokens_used`，pop 后再 validate 成 Decision：

```python
# app/agent/conductor.py _decide
raw = self.llm.complete_tool_call(...)
tokens_used = raw.pop("_tokens_used", 0)
decision = Decision.model_validate(raw)
# 在 run 里把 tokens_used 写进 ToolCall
```

新增成本汇总 API：

```python
# app/agent/store.py
def session_cost_summary(session_id: str) -> dict:
    state = load_state(session_id)
    if not state:
        return {}
    total_tokens = sum(step.tokens_used for step in state.steps)
    total_latency = sum(step.latency_ms for step in state.steps)
    return {
        "session_id": session_id,
        "total_tokens": total_tokens,
        "total_latency_ms": total_latency,
        "tool_count": len(state.steps),
        "tools_by_latency": sorted(
            [{"name": s.tool_name, "ms": s.latency_ms} for s in state.steps],
            key=lambda x: -x["ms"],
        )[:5],
        "estimated_cost_usd": round(total_tokens * 0.0000002, 6),   # DeepSeek 价格
    }
```

```python
# app/api/routes_agent.py
@router.get("/cost/{session_id}")
def get_session_cost(session_id: str) -> dict:
    summary = session_cost_summary(session_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Session not found")
    return summary
```

### 2.4 OpenTelemetry 链路追踪（可选加分项）

```bash
pip install opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-fastapi opentelemetry-exporter-otlp
```

```python
# app/observability/tracing.py
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter


def configure_otel(service_name: str = "airoute-agent", endpoint: str | None = None) -> None:
    if not endpoint:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
    trace.set_tracer_provider(provider)


tracer = trace.get_tracer(__name__)
```

`tools.py` 每个 handler 开 span：

```python
def _recommend_pool(state, args):
    with tracer.start_as_current_span("tool.recommend_pool") as span:
        span.set_attribute("city", str(args.get("city")))
        span.set_attribute("user_id", state.goal.user_id)
        # ... 已有逻辑
        span.set_attribute("pool_size", pool.meta.total_count)
        return ToolResult(...)
```

接 Jaeger / Tempo / Honeycomb 看完整调用链。本地用 Docker 起 `jaegertracing/all-in-one:latest`，端口 16686 看 trace 树。

### 2.5 验收

```bash
# 跑一次 agent run
curl -X POST localhost:8000/api/agent/run -d '{...}'

# 看指标
curl localhost:8000/metrics | grep agent_

# 看成本汇总
curl localhost:8000/api/agent/cost/<session_id>

# 看日志（JSON 格式）
tail -f logs/app.log | jq
```

期望看到 `agent_tool_latency_seconds_count{tool_name="parse_intent"} > 0`、成本汇总返回非 0 token、日志带 session_id / trace_id contextvars。

---

## 三、缓存策略与 Redis 适用性判断（1 天）

### 3.1 项目里需要被缓存的对象盘点

按访问频次 × 计算成本 × 数据稳定性三维评估：

| 对象 | 访问频次 | 计算成本 | 数据稳定性 | 缓存价值 | 当前实现 |
|---|---|---|---|---|---|
| Amap 路段（origin+dest+mode） | 高 | 高（HTTP + 配额） | 永久 | 极高 | **无** |
| LLM 决策响应（同 prompt） | 中 | 高（token 钱 + 延迟） | 5 分钟级 | 高 | **无** |
| BGE query embedding | 高（每次 search） | 中（CPU 50ms） | 永久 | 高 | **无** |
| `UserFacts` derive | 中 | 中（多 session join） | 5 分钟级 | 高 | SQLite + 内存 `_CACHE` ✅ |
| `PoiRepository` 全表 | 极高 | 低（一次性加载） | 永久 | 极高 | `lru_cache` ✅ |
| `UgcVectorRepo` FAISS 索引 | 高 | 中（mmap） | 永久 | 高 | 单例 instance ✅ |
| `SessionVectorRepo` per-user 索引 | 中 | 中 | 5 分钟级 | 中 | dict 缓存 ✅ |
| 候选池（PoolResponse） | 中 | 高（评分 + 排序） | session 级 | 中 | 无（每次重算） |

绿色对勾的已有缓存机制。需要补的是 **Amap 路段、LLM 决策、BGE query embedding** 这三类——共同点是"外部依赖、有钱 / 配额成本、可缓存窗口长"。

### 3.2 Amap 路段缓存（SQLite 实现）

最高 ROI 的一个缓存——Amap 免费 key 日 5000 次，连续 demo 一炸就完。

```python
# app/services/amap/cache.py
import json
import sqlite3
from pathlib import Path

from app.services.amap.schemas import AmapRouteMode, AmapRouteResult, AmapRouteStep


PROJECT_ROOT = Path(__file__).resolve().parents[4]
CACHE_DB = PROJECT_ROOT / "data" / "processed" / "amap_cache.sqlite"
_SCHEMA = """
CREATE TABLE IF NOT EXISTS amap_segments (
    cache_key TEXT PRIMARY KEY,
    distance_m REAL NOT NULL,
    duration_s REAL NOT NULL,
    steps_json TEXT NOT NULL,
    raw_response_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    hit_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_amap_created ON amap_segments(created_at DESC);
"""


def _conn():
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CACHE_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn


def cache_key(*, mode: str, origin_lon: float, origin_lat: float,
              dest_lon: float, dest_lat: float) -> str:
    # 6 位精度约 0.1m，足够区分；小数过多反而 key 太碎
    return f"{mode}:{origin_lon:.6f},{origin_lat:.6f}->{dest_lon:.6f},{dest_lat:.6f}"


def get_cached(key: str) -> AmapRouteResult | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT distance_m, duration_s, steps_json, raw_response_json FROM amap_segments WHERE cache_key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        conn.execute("UPDATE amap_segments SET hit_count = hit_count + 1 WHERE cache_key = ?", (key,))
    steps_data = json.loads(row[2])
    return AmapRouteResult(
        mode=AmapRouteMode(key.split(":", 1)[0]),
        distance_m=row[0],
        duration_s=row[1],
        steps=[AmapRouteStep(**s) for s in steps_data],
        polyline_coordinates=[c for s in steps_data for c in s.get("polyline_coordinates", [])],
        raw_response=json.loads(row[3]) if row[3] else {},
    )


def set_cached(key: str, result: AmapRouteResult) -> None:
    steps_data = [
        {
            "instruction": step.instruction,
            "road_name": step.road_name,
            "distance_m": step.distance_m,
            "duration_s": step.duration_s,
            "polyline_coordinates": step.polyline_coordinates,
        }
        for step in result.steps
    ]
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO amap_segments (cache_key, distance_m, duration_s, steps_json, raw_response_json) VALUES (?, ?, ?, ?, ?)",
            (key, result.distance_m, result.duration_s, json.dumps(steps_data), json.dumps(result.raw_response)),
        )
```

`AmapRouteClient.get_route` 入口包上：

```python
# app/services/amap/client.py
from app.services.amap import cache as amap_cache
from app.observability.metrics import AMAP_REQUESTS, CACHE_HIT_RATE

class AmapRouteClient:
    def get_route(self, *, mode, origin, destination):
        key = amap_cache.cache_key(
            mode=mode.value if hasattr(mode, "value") else str(mode),
            origin_lon=origin.longitude, origin_lat=origin.latitude,
            dest_lon=destination.longitude, dest_lat=destination.latitude,
        )
        cached = amap_cache.get_cached(key)
        if cached is not None:
            AMAP_REQUESTS.labels(mode=str(mode), status="ok", cache="hit").inc()
            CACHE_HIT_RATE.labels(cache_name="amap_segment", result="hit").inc()
            return cached
        CACHE_HIT_RATE.labels(cache_name="amap_segment", result="miss").inc()
        result = self._raw_get_route(mode=mode, origin=origin, destination=destination)
        amap_cache.set_cached(key, result)
        AMAP_REQUESTS.labels(mode=str(mode), status="ok", cache="miss").inc()
        return result

    def _raw_get_route(self, ...):   # 把原来 get_route 的实现搬到这里
        ...
```

预计命中率：合肥同区域内 POI 反复出现，连续 demo 跑同一组用户 → 命中率 60-80%。Amap 配额压力降一个量级。

### 3.3 LLM 决策响应缓存（in-memory TTL）

```python
# app/llm/cache.py
import hashlib
import json
from cachetools import TTLCache
from threading import Lock


_CACHE: TTLCache = TTLCache(maxsize=2000, ttl=300)   # 5 分钟
_LOCK = Lock()


def cache_key(prompt: str, tools: list[dict], system_prompt: str | None = None) -> str:
    payload = json.dumps(
        {
            "prompt": prompt,
            "system_prompt": system_prompt,
            "tools": [t.get("name") for t in tools] if tools else None,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get(key: str):
    with _LOCK:
        return _CACHE.get(key)


def put(key: str, value: dict) -> None:
    with _LOCK:
        _CACHE[key] = value
```

`LlmClient.complete_tool_call` 接入：

```python
# app/llm/client.py
from app.llm import cache as llm_cache
from app.observability.metrics import CACHE_HIT_RATE

def complete_tool_call(self, prompt, *, tools, fallback):
    if not get_settings().llm_api_key:
        return fallback
    key = llm_cache.cache_key(prompt, tools, "Choose exactly one tool. Return only a tool call.")
    cached = llm_cache.get(key)
    if cached is not None:
        CACHE_HIT_RATE.labels(cache_name="llm_tool_call", result="hit").inc()
        return cached
    CACHE_HIT_RATE.labels(cache_name="llm_tool_call", result="miss").inc()
    # ... 已有 HTTP 调用
    try:
        # ... 拿到 tool_calls 后
        result = {"tool": tool_name, "args": args}
        llm_cache.put(key, result)
        return result
    except Exception:
        return fallback
```

注意几点：

- 只缓存成功返回的 result，不缓存 fallback（fallback 是失败兜底）
- TTL 5 分钟在 demo 场景够用，生产场景同 query 可能想要不同结果时调小
- `complete_json` 同样可以套（譬如 StoryAgent / RepairAgent 的 prompt 调用），但小心 StoryAgent 是创造性输出可能不希望被缓存——给 `complete_json` 加 `cacheable: bool = False` 默认关，只在确定无副作用的地方开

### 3.4 BGE query embedding 缓存

UgcVectorRepo 和 SessionVectorRepo 每次 search 都调一次 BGE encode，CPU 上约 50ms。对同一 query 短期重复请求（譬如同用户多次 refresh）浪费明显。

```python
# app/repositories/embedding_cache.py
import hashlib
from cachetools import LRUCache
from threading import Lock


_CACHE: LRUCache = LRUCache(maxsize=500)   # 500 条 × 512 维 × 4 字节 = 1MB 内存
_LOCK = Lock()


def cache_key(model_name: str, text: str) -> str:
    return hashlib.md5(f"{model_name}|{text}".encode("utf-8")).hexdigest()


def get(key: str):
    with _LOCK:
        return _CACHE.get(key)


def put(key: str, embedding) -> None:
    with _LOCK:
        _CACHE[key] = embedding
```

```python
# app/repositories/ugc_vector_repo.py 修改 _encode 风格的 wrap
def _encode_cached(self, text: str):
    from app.repositories import embedding_cache
    key = embedding_cache.cache_key(MODEL_NAME, text)
    cached = embedding_cache.get(key)
    if cached is not None:
        return cached
    embedding = self._encode(text)
    if embedding is not None:
        embedding_cache.put(key, embedding)
    return embedding
```

调用方从 `self._encode(query)` 改为 `self._encode_cached(query)`。SessionVectorRepo 同样改造。LRU 而非 TTL，因为 embedding 模型不变结果永远一致。

### 3.5 关键问题：要不要换 Redis？

**结论：现在不需要，未来在三个明确触发点之一发生时再迁移。**

#### 为什么现在不需要

当前部署形态是单进程 uvicorn + SQLite + 本地文件 + 内存 lru_cache。在这套架构下 Redis 带来的收益不抵成本：

- **没有跨进程共享需求**。所有缓存对象都在同一个 Python 进程内复用，`TTLCache` 和 `lru_cache` 就够了。
- **网络延迟反而拖慢**。Redis 单次 GET/SET 约 1-5ms（同机房）；in-memory dict 是 0.1μs 级别。对 BGE embedding 这种 50ms 的操作 Redis 还行，但对 LLM 缓存（命中后 0 延迟）改成 Redis 反而引入 1ms 开销。
- **持久化 Amap 缓存不需要 Redis**。SQLite WAL 模式单线程写入 5000+ QPS，足够支撑现状负载。
- **额外的依赖与运维成本**。免费层（Railway/Render）启动 Redis 实例要么收钱要么走 Upstash 等托管，部署复杂度上一档。

#### 三个迁移触发点

下面任一条件成立时，转向 Redis 才有正向 ROI：

**触发点 1：uvicorn 启用多 worker 部署**（最常见触发原因）

```bash
uvicorn app.main:app --workers 4
```

多 worker 后内存 cache 各 worker 独立，缓存命中率被切到 1/4，且 user_facts 在 worker A 失效时 worker B 不知道。这时候需要：

- `cachetools.TTLCache` → Redis with TTL
- `_QUEUES` (SSE 订阅队列) → Redis Pub/Sub（不然 SSE 流式跨 worker 收不到事件）
- `_EVENTS` trace dict → Redis list / stream
- `SessionVectorRepo._indexes` 字典缓存 → 仍可保留本地（每个 worker mmap 同一文件即可）

**触发点 2：横向扩展到多实例**

部署多个 backend 实例（譬如 Railway 的 replicas=2）+ 前面挂 LB。这时 sticky session 不可靠（用户每次请求可能命中不同实例），任何"会话上下文"必须共享：

- `agent_sessions.sqlite` → Postgres（SQLite 不支持多实例并发写）
- 进程内所有 cache → Redis
- SSE 推送 → Redis Pub/Sub 或 NATS

**触发点 3：需要实时流式跨实例**

譬如 demo 时一个用户从 A 实例发起 `/api/agent/run`，从 B 实例订阅 `/api/agent/stream/{id}`——SSE 跨实例必须靠 Pub/Sub。Redis 是最简实现：

```python
# app/agent/tracing.py 改造（Redis 版）
import json
import redis.asyncio as redis

_redis: redis.Redis | None = None

async def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = await redis.from_url(get_settings().redis_url)
    return _redis

async def record_event_async(session_id: str, event: dict) -> None:
    r = await get_redis()
    await r.xadd(f"trace:{session_id}", {"data": json.dumps(event)}, maxlen=100)
    await r.publish(f"trace_pubsub:{session_id}", json.dumps(event))

async def subscribe_async(session_id: str):
    r = await get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(f"trace_pubsub:{session_id}")
    async for message in pubsub.listen():
        if message["type"] == "message":
            yield json.loads(message["data"])
```

#### 迁移友好的抽象层（现在就可以加）

即使现在不引 Redis，可以先抽出 `CacheBackend` 接口，让未来切换零代码改动：

```python
# app/observability/cache_backend.py
from typing import Protocol, Any
from cachetools import TTLCache, LRUCache
from threading import Lock


class CacheBackend(Protocol):
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl: int | None = None) -> None: ...
    def delete(self, key: str) -> None: ...


class InMemoryTTLBackend:
    def __init__(self, maxsize: int = 1000, default_ttl: int = 300):
        self._cache = TTLCache(maxsize=maxsize, ttl=default_ttl)
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            return self._cache.get(key)

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        with self._lock:
            self._cache[key] = value     # TTLCache 用构造时的 ttl

    def delete(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)


class RedisBackend:
    def __init__(self, url: str):
        import redis
        self._client = redis.from_url(url, decode_responses=False)

    def get(self, key: str):
        raw = self._client.get(key)
        if raw is None:
            return None
        import pickle
        return pickle.loads(raw)

    def set(self, key: str, value, ttl: int | None = None) -> None:
        import pickle
        self._client.set(key, pickle.dumps(value), ex=ttl)

    def delete(self, key: str) -> None:
        self._client.delete(key)


def get_default_backend() -> CacheBackend:
    settings = get_settings()
    if getattr(settings, "redis_url", ""):
        return RedisBackend(settings.redis_url)
    return InMemoryTTLBackend()
```

`llm/cache.py`、`embedding_cache.py` 都改用这个接口。config.py 加 `redis_url: str = ""`，默认空字符串就走内存，未来部署到多实例时 `REDIS_URL=redis://...` 切换。

简历可写："Pluggable cache backend abstraction supporting in-memory TTL (default) and Redis (multi-worker / multi-instance deployments)."

### 3.6 缓存策略验收

```bash
# 跑两次相同 query 看命中
curl -X POST localhost:8000/api/agent/run -d '{"user_id":"a","free_text":"火锅",...}'
curl -X POST localhost:8000/api/agent/run -d '{"user_id":"a","free_text":"火锅",...}'

# 看指标，应该看到 hit 计数增加
curl localhost:8000/metrics | grep agent_cache_hits
curl localhost:8000/metrics | grep agent_amap_requests.*cache

# 看 amap 缓存表
sqlite3 data/processed/amap_cache.sqlite "SELECT COUNT(*), AVG(hit_count) FROM amap_segments"
```

期望第二次 run 的 Amap calls 从 4 降到 0（全命中），LLM 决策调用从 ~7 降到 ~7（首次无变化）；同一 user 短时间第三次 run 时 LLM decision 命中率上升。

---

## 四、质量工程（1 天）

把 agent 输出的"质量"从感性判断变成可量化、可回归、可 CI 卡门禁的工程指标。

### 4.1 Prompt 文件化与版本号

当前 prompt 散落在三处：`StoryAgent._build_prompt`、`Critic._build_prompt`、`RepairAgent._build_prompt`，且 `prompts/story.system.md` 和 `critic.system.md` 已经存在但内容简陋且不被代码引用。

集中重写 + 版本号：

```markdown
<!-- app/agent/prompts/story.system.md -->
<!-- version: v1.2.0 -->
<!-- last_updated: 2026-05-15 -->

你是 AIroute 的路线编剧（StoryAgent）。

任务：给用户编一条 3-5 站、带主题的合肥半日路线。每站有清晰角色（opener / midway / main / rest / closer），并引用 UGC 原文做证据。

约束：
- 必须包含 1 家餐饮（restaurant 类），可选 1 个 cafe 类作为休息节点
- 总时长不超过用户时间窗，预算超 20% 以内可接受
- 用户必去 POI（must_visit）必须全部包含
- 用户排除 POI（avoid）必须排除
- 只能用候选清单里的 POI，不能编造
- 只能引用候选清单里附带的 UGC quote_ref，不能编造

输入：
- query: 用户自由文本
- candidates: 候选 POI 列表（含 quote_ref 和 quote）
- past sessions: 用户历史路线摘要（避免重复主题）
- similar sessions: 语义相似的过往路线（参考但不重复）
- user_facts: 用户的偏好画像

输出 JSON：
{
  "theme": "8-12 字的主题",
  "narrative": "60-100 字的总叙述",
  "stops": [
    {
      "poi_id": "候选清单中的 ID",
      "role": "opener|midway|main|rest|closer",
      "why": "30-50 字，必须嵌入一句 UGC 原文",
      "ugc_quote_ref": "候选清单中的 post_id",
      "ugc_quote": "对应的 UGC 原文",
      "suggested_dwell_min": 整数
    }
  ],
  "dropped": [
    {"poi_id": "...", "reason": "..."}
  ],
  "fallback_used": false
}
```

```python
# app/agent/prompts/__init__.py
import re
from functools import lru_cache
from pathlib import Path


PROMPTS_DIR = Path(__file__).resolve().parent
VERSION_PATTERN = re.compile(r"<!--\s*version:\s*(v[\d.]+)\s*-->")


@lru_cache
def load_prompt(name: str) -> tuple[str, str]:
    """Returns (content, version)"""
    path = PROMPTS_DIR / f"{name}.system.md"
    content = path.read_text(encoding="utf-8")
    match = VERSION_PATTERN.search(content)
    version = match.group(1) if match else "unversioned"
    return content, version


def get_prompt_version(name: str) -> str:
    _, version = load_prompt(name)
    return version
```

`StoryAgent.compose` 改为读文件：

```python
# app/agent/specialists/story_agent.py
from app.agent.prompts import load_prompt

class StoryAgent:
    def compose(self, state):
        # ... 已有 fallback 逻辑
        if not settings.agent_tool_calling_enabled or not settings.llm_api_key:
            return fallback
        
        system_prompt, prompt_version = load_prompt("story")
        raw = self.llm.complete_json(
            self._build_prompt(candidates, state),
            fallback=fallback.model_dump(),
            agent_name="story_planner",
            system_prompt=system_prompt,
        )
        # 把 prompt_version 记到 trace 里
        # ...
```

`ToolCall.observation_payload_ref` 字段写 `f"prompt:story@{prompt_version}"`，trace 里能看到本次用的 prompt 版本。

### 4.2 Prompt 回归集

```python
# tests/prompt_eval/story.eval.jsonl
{"id": "case_local_food", "input": {"query": "想吃合肥本地菜，少排队", "city": "hefei"}, "expected": {"min_stops": 3, "max_stops": 5, "must_include_categories": ["restaurant"], "theme_must_contain_any": ["本地", "合肥", "庐州"]}}
{"id": "case_rainy_indoor", "input": {"query": "下雨天，找个室内不无聊的", "city": "hefei"}, "expected": {"min_stops": 3, "max_stops": 5, "forbidden_categories": ["outdoor"]}}
{"id": "case_friends_evening", "input": {"query": "晚上和朋友聚聚，预算150", "city": "hefei"}, "expected": {"min_stops": 3, "max_stops": 5, "max_budget_violation_ratio": 0.2}}
... 共 12 条
```

```python
# tests/test_prompt_regression.py
import json
import os
from pathlib import Path

import pytest

from app.api.routes_agent import AgentRunRequest, build_initial_state
from app.agent.conductor import Conductor
from app.agent.tools import get_tool_registry
from app.llm.client import LlmClient
from app.repositories.poi_repo import get_poi_repository


PROMPT_EVAL_PATH = Path(__file__).parent / "prompt_eval" / "story.eval.jsonl"
PASS_RATE_GATE = 0.85


@pytest.mark.skipif(
    not os.getenv("RUN_LLM_EVAL"),
    reason="LLM regression eval requires API key; set RUN_LLM_EVAL=1 to enable",
)
def test_story_prompt_regression_pass_rate(monkeypatch):
    _patch_route_client_with_fake(monkeypatch)
    
    cases = [
        json.loads(line)
        for line in PROMPT_EVAL_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    repo = get_poi_repository()
    
    results = []
    for case in cases:
        state = _run_one_case(case)
        ok, detail = _evaluate(state, case, repo)
        results.append({"case": case["id"], "passed": ok, "detail": detail})
    
    output = Path("data/eval/prompt_regression.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    
    passed = sum(1 for r in results if r["passed"])
    pass_rate = passed / len(results)
    print(f"\nPrompt regression: {passed}/{len(results)} = {pass_rate:.0%}")
    assert pass_rate >= PASS_RATE_GATE, f"Pass rate {pass_rate:.0%} below gate {PASS_RATE_GATE:.0%}"


def _evaluate(state, case, repo) -> tuple[bool, dict]:
    story = state.memory.story_plan
    if story is None:
        return False, {"reason": "no_story_plan"}
    expected = case["expected"]
    
    checks = {
        "stops_in_range": expected.get("min_stops", 0) <= len(story.stops) <= expected.get("max_stops", 99),
        "evidence_grounded": all(s.ugc_quote_ref and s.ugc_quote for s in story.stops),
    }
    
    categories = {repo.get(s.poi_id).category for s in story.stops if _safe_get(repo, s.poi_id)}
    if "must_include_categories" in expected:
        checks["categories_included"] = set(expected["must_include_categories"]) <= categories
    if "forbidden_categories" in expected:
        checks["no_forbidden"] = not (set(expected["forbidden_categories"]) & categories)
    
    if "theme_must_contain_any" in expected:
        checks["theme_match"] = any(t in (story.theme or "") for t in expected["theme_must_contain_any"])
    
    return all(checks.values()), checks
```

CI 跑 `RUN_LLM_EVAL=1 pytest tests/test_prompt_regression.py` 作为可选 gate。改 prompt 后必须 ≥85% 通过才允许 merge。日常 CI 不带 `RUN_LLM_EVAL` 跳过，避免每次 push 都消耗 token。

### 4.3 LLM-as-Judge 质量评估

用强模型（譬如 DeepSeek-V3）当裁判，判定 agent 输出质量比硬规则更细：

```python
# tests/test_agent_quality.py
import json
import os
from pathlib import Path

import httpx
import pytest


JUDGE_SYSTEM = """
你是路线方案质量裁判。对给定的用户 query 和 agent 输出的路线方案，按下面 5 个维度 0-10 打分：

- theme_coherence: 主题与 query 的契合度
- evidence_grounding: 每个停留点的 UGC 引用是否真实贴切
- pacing: 时间节奏是否合理（不赶、不空）
- preference_fit: 是否符合用户隐含偏好（party_type / budget / 时段）
- narrative_quality: 总叙述是否吸引人

返回严格 JSON：
{
  "theme_coherence": int,
  "evidence_grounding": int,
  "pacing": int,
  "preference_fit": int,
  "narrative_quality": int,
  "overall_comment": "30 字内"
}
"""


@pytest.mark.skipif(
    not os.getenv("RUN_LLM_JUDGE"),
    reason="LLM-as-judge eval requires JUDGE_LLM_API_KEY",
)
def test_agent_output_quality_via_judge():
    queries = [
        "想吃合肥本地菜，少排队",
        "晚上和朋友聚聚，预算150",
        "下雨天，找个室内吃点好的",
    ]
    
    judge_scores = []
    for query in queries:
        state = _run_agent_with_query(query)
        story = state.memory.story_plan
        assert story is not None, f"Agent failed for query: {query}"
        
        judge_input = f"User query: {query}\n\nAgent story plan: {story.model_dump_json()}"
        result = _invoke_judge(JUDGE_SYSTEM, judge_input)
        judge_scores.append({"query": query, "scores": result})
    
    output = Path("data/eval/judge_scores.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(judge_scores, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # 5 维平均分必须 ≥ 7
    for entry in judge_scores:
        scores = entry["scores"]
        avg = sum(scores[k] for k in ["theme_coherence", "evidence_grounding", "pacing", "preference_fit", "narrative_quality"]) / 5
        assert avg >= 7, f"Query {entry['query']!r} got avg {avg:.1f} < 7"


def _invoke_judge(system: str, user_input: str) -> dict:
    """用 DeepSeek-V3 作为裁判模型（独立的 API key 避免污染主链路指标）"""
    response = httpx.post(
        "https://api.deepseek.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {os.environ['JUDGE_LLM_API_KEY']}",
            "Content-Type": "application/json",
        },
        json={
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_input},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        },
        timeout=30,
    )
    response.raise_for_status()
    return json.loads(response.json()["choices"][0]["message"]["content"])
```

这一项是 2024-2025 年 agent 团队的标配。简历可直接写："LLM-as-judge quality evaluation in CI with 5-dimensional scoring (theme coherence, evidence grounding, pacing, preference fit, narrative quality)."

### 4.4 Snapshot 测试

`StoryPlan` / `AgentRunResponse` 的输出格式很容易被意外改坏。加快照：

```bash
pip install syrupy
```

```python
# tests/test_agent_snapshots.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_agent_run_response_shape(snapshot, monkeypatch):
    _patch_route_client_with_fake(monkeypatch)
    
    response = client.post(
        "/api/agent/run",
        json={
            "user_id": "snapshot_user",
            "free_text": "fixed query for snapshot",
            "city": "hefei",
            "date": "2026-05-08",
            "time_window": {"start": "12:00", "end": "20:00"},
            "budget_per_person": 180,
        },
    )
    assert response.status_code == 200
    body = response.json()
    
    # 只断言 schema 形状，不断言具体内容（避免 POI 选择变化导致 snapshot 改）
    shape = _extract_shape(body)
    assert shape == snapshot
```

```python
def _extract_shape(obj):
    """递归提取 schema 形状（key + type），忽略具体值"""
    if isinstance(obj, dict):
        return {k: _extract_shape(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        if not obj:
            return []
        return [_extract_shape(obj[0])]
    return type(obj).__name__
```

`pytest --snapshot-update` 刷新快照。改 schema 时 CI 看到 snapshot diff 就要显式批准。

### 4.5 Mypy 严格类型

```toml
# backend/pyproject.toml
[tool.mypy]
python_version = "3.12"
strict = true
exclude = ["tests/", "scripts/"]
ignore_missing_imports = true
warn_unused_ignores = true
warn_return_any = true

[[tool.mypy.overrides]]
module = ["sentence_transformers.*", "faiss.*", "chromadb.*", "structlog.*"]
ignore_missing_imports = true
```

CI 跑 `mypy app/`。当前代码估计会有 50+ 个 `Any` 警告，逐个修。修完后 agent 内部数据流的类型完全收紧，新成员接手时 IDE 自动补全和重构都准确得多。

### 4.6 质量工程验收

```bash
# Prompt 回归（消耗 token，可选）
RUN_LLM_EVAL=1 pytest tests/test_prompt_regression.py -v
cat data/eval/prompt_regression.json | jq '. | length, [.[] | select(.passed)] | length'

# LLM-as-judge（消耗 token，可选）
JUDGE_LLM_API_KEY=xxx RUN_LLM_JUDGE=1 pytest tests/test_agent_quality.py -v
cat data/eval/judge_scores.json | jq '[.[] | .scores | values | add / 5] | add / length'

# Snapshot
pytest tests/test_agent_snapshots.py -v

# 类型检查
mypy app/
```

期望：

- 回归通过率 ≥ 85%
- 裁判 5 维平均分 ≥ 7
- snapshot 测试全绿（除非主动修改 schema）
- mypy 0 error

---

## 五、四节总时间表

| 节 | 内容 | 工时 | 里程碑 |
|---|---|---|---|
| 一 | 扫尾遗留 6 项 | 半天 | `test_user_facts.py` + `test_episodic_memory.py` 全绿 |
| 二 | 日志 + 指标 + 成本追踪 | 1 天 | `/metrics` 暴露所有自定义指标，`/api/agent/cost/{id}` 返回成本 |
| 三 | Amap + LLM + Embedding 三级缓存 | 1 天 | 第二次相同请求 Amap calls 降至 0，命中率 ≥ 60% |
| 四 | Prompt 文件化 + 回归集 + judge + snapshot + mypy | 1 天 | CI 含 prompt 回归 gate，mypy 0 error |

总计 3.5 天，按"扫尾 → 可观测 → 缓存 → 质量"顺序推进。每节独立 commit 且独立验收，每节做完都能立刻提升一个工程维度。

---

## 六、Redis 决策小结

不要现在引入 Redis。当且仅当下面三个条件之一出现时迁移：

1. **`uvicorn --workers > 1`**——多 worker 后内存 cache 不能跨 worker 共享，SSE 跨 worker 收不到事件
2. **横向扩展到多实例**——譬如 Render replicas=2，必须共享 session 状态
3. **跨实例实时流式需求**——demo 用户从 A 实例发起 run、从 B 实例订阅 stream

迁移成本可控：第三节 3.5 节给出的 `CacheBackend` 接口现在就抽出来，三个触发点出现时只需要在配置里加 `REDIS_URL=...`，应用代码零改动。

简历表达：

> Pluggable cache backend abstraction (in-memory TTL default, Redis-ready for multi-worker / multi-instance deployments); SQLite-backed Amap segment cache reduces external API calls by 60-80% in repeated queries.

---

## 七、收尾原则

按以下三条优先级排序解决冲突：

1. **先扫尾再加新东西**。第一节六项做完前不开始第二节，避免在脏代码上叠新逻辑。
2. **每节做完跑全套测试**。新加的可观测性、缓存、prompt 改动都可能破坏已有 30+ 测试，每节结束 `pytest -v` 必须全绿。
3. **CI gate 一次只加一个**。先加 mypy gate，绿后加 snapshot gate，绿后加 prompt 回归 gate。一次加多个 gate 任何一个挂都阻塞 merge。

3.5 天后 AIroute 从"功能完整 + 三层记忆"升到"production observability + cached + quality-gated"的工程闭环形态。

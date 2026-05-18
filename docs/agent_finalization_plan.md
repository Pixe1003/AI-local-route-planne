# AIroute Agent 收尾开发方案

> 在团队已完成四阶段骨架（Conductor + 5 个 Specialist + Tool Registry + RAG + Tracing + 前端可视化）的基础上，把项目从"能跑"推到"工程闭环、对外可演、可复现"的程度。
>
> 假设：剩余预算 5-7 天专注开发。

---

## 零、现状盘点

**已完成**（核心架构就位）：

- `app/agent/` 全套：`conductor.py / state.py / tools.py / tool_schemas.py / store.py / tracing.py / story_models.py`
- 9 个工具注册：`parse_intent / search_ugc_evidence / recommend_pool / compose_story / get_amap_chain / parse_feedback / replan_by_event / validate_route / critique`
- LLM tool calling（OpenAI tools 协议）+ 规则降级序列双轨
- StoryAgent（含 post_check 幻觉检测）、Critic（5 维评分 + should_stop 触发重试）、RepairAgent
- `data/processed/ugc_hefei.jsonl`：真合成的 UGC 语料，每 POI 三条 130-180 字带情感细节的中文评论
- `UgcVectorRepo` 抽象层 + lexical 检索 + `evidence_for_poi`
- `routes_agent.py`：`/run /adjust /trace /stream` 四端点
- 前端 `AgentThinkingPanel` 组件 + `AmapRoutePage` 展示 theme / narrative / ugc_quote
- 16 个 pytest 测试覆盖四阶段

**待补全**（下面五块硬伤 + 三块加分 + 四类收尾工程）。

---

## 一、五块硬伤（必修）

### 1.1 `/api/agent/tools` 端点缺失（10 分钟）

`test_agent_stage4.py:test_agent_tools_endpoint_exposes_feedback_tools` 引用了 `GET /api/agent/tools`，但 `routes_agent.py` 没实现。测试当前会失败。

```python
# app/api/routes_agent.py
@router.get("/tools")
def list_agent_tools() -> list[dict]:
    return get_tool_registry().schemas_for_llm()
```

修复后 `test_agent_stage4` 全绿。也方便运维/调试时直接 `curl /api/agent/tools | jq` 看注册工具状态。

### 1.2 SSE 流式不真（4 小时）

当前 `stream_trace`：

```python
return StreamingResponse(
    iter([format_sse(get_trace_events(session_id))]),
    media_type="text/event-stream",
)
```

`iter([...])` 一次性把所有事件拼成一坨返回——只有 agent 跑完之后才能看到，不是"思考过程"。前端 EventSource 收不到增量。

修复用 asyncio.Queue + 后台任务推送：

```python
# app/agent/tracing.py
import asyncio
from collections import defaultdict

_QUEUES: dict[str, list[asyncio.Queue]] = defaultdict(list)
_EVENTS: dict[str, list[dict]] = defaultdict(list)

def subscribe(session_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _QUEUES[session_id].append(q)
    return q

def record_event(session_id: str, event: dict) -> None:
    _EVENTS[session_id].append(event)
    for q in _QUEUES.get(session_id, []):
        q.put_nowait(event)

def unsubscribe(session_id: str, queue: asyncio.Queue) -> None:
    queues = _QUEUES.get(session_id, [])
    if queue in queues:
        queues.remove(queue)
```

```python
# app/api/routes_agent.py
@router.post("/run")
async def run_agent(req: AgentRunRequest) -> AgentRunResponse:
    state = build_initial_state(req)
    loop = asyncio.get_event_loop()
    final = await loop.run_in_executor(
        None,
        lambda: Conductor(get_tool_registry(), LlmClient()).run(state),
    )
    save_state(final)
    return _response_from_state(final)

@router.get("/stream/{session_id}")
async def stream_trace(session_id: str) -> StreamingResponse:
    async def gen():
        q = subscribe(session_id)
        try:
            for event in get_trace_events(session_id):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") in {"finished", "failed"}:
                    break
        finally:
            unsubscribe(session_id, q)
    return StreamingResponse(gen(), media_type="text/event-stream")
```

前端把 `routeRequest.agent_steps` 静态展示换成 `useEffect` + `new EventSource("/api/agent/stream/...")` 实时收事件，逐条 append 进 `AgentThinkingPanel`。

### 1.3 `UgcVectorRepo` 名实不符——补真 embedding（1-2 天）

类名叫 Vector，实际是 token 重叠 + 子串匹配。语义检索能力差，且对外接口名误导。

**第一步：写离线 embedding 脚本**

```python
# scripts/embed_ugc.py
from pathlib import Path
import json
import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
DATA_PATH = Path("data/processed/ugc_hefei.jsonl")
EMBED_PATH = Path("data/processed/ugc_hefei_embeddings.npy")
META_PATH = Path("data/processed/ugc_hefei_meta.jsonl")


def main() -> None:
    model = SentenceTransformer(MODEL_NAME)
    texts: list[str] = []
    metas: list[dict] = []
    with DATA_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            for review in row.get("reviews", []):
                content = (review.get("content") or "").strip()
                if not content:
                    continue
                texts.append(content)
                metas.append({
                    "poi_id": row["poi_id"],
                    "poi_name": row.get("poi_name"),
                    "sub_category": row.get("sub_category"),
                    "district": row.get("district"),
                    "rating": review.get("rating"),
                    "content": content,
                    "post_id": f"ugc_{row['poi_id']}_{len(texts):05d}",
                })

    print(f"Encoding {len(texts)} reviews...")
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=True,
        batch_size=32,
    )
    np.save(EMBED_PATH, embeddings.astype("float32"))
    with META_PATH.open("w", encoding="utf-8") as f:
        for meta in metas:
            f.write(json.dumps(meta, ensure_ascii=False) + "\n")
    print(f"Saved {len(embeddings)} embeddings to {EMBED_PATH}")


if __name__ == "__main__":
    main()
```

**第二步：改造 UgcVectorRepo**

```python
# app/repositories/ugc_vector_repo.py
class UgcVectorRepo:
    def __init__(
        self,
        data_path: str | Path | None = None,
        *,
        embed_path: Path | None = None,
        meta_path: Path | None = None,
    ) -> None:
        self.data_path = _resolve_data_path(data_path)
        self._embed_path = embed_path or PROJECT_ROOT / "data/processed/ugc_hefei_embeddings.npy"
        self._meta_path = meta_path or PROJECT_ROOT / "data/processed/ugc_hefei_meta.jsonl"
        self._reviews: list[UgcReview] | None = None
        self._model = None
        self._embeddings = None
        self._metas: list[dict] | None = None

    def _ensure_embeddings(self) -> bool:
        if self._embeddings is not None:
            return True
        if not (self._embed_path.exists() and self._meta_path.exists()):
            return False
        try:
            import numpy as np
            from sentence_transformers import SentenceTransformer
        except ImportError:
            return False
        self._embeddings = np.load(self._embed_path)
        self._metas = [
            json.loads(line) for line in self._meta_path.open(encoding="utf-8") if line.strip()
        ]
        self._model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
        return True

    def search(self, query: str, *, city: str | None = "hefei",
               poi_id: str | None = None, top_k: int = 8) -> list[UgcSearchHit]:
        if self._ensure_embeddings() and query:
            return self._search_semantic(query, poi_id=poi_id, top_k=top_k)
        return self._search_lexical(query, city=city, poi_id=poi_id, top_k=top_k)

    def _search_semantic(self, query: str, *, poi_id: str | None,
                         top_k: int) -> list[UgcSearchHit]:
        import numpy as np
        q_emb = self._model.encode(query, normalize_embeddings=True).astype("float32")
        scores = self._embeddings @ q_emb
        mask = np.ones(len(scores), dtype=bool)
        if poi_id:
            mask = np.array([m["poi_id"] == poi_id for m in self._metas], dtype=bool)
            scores = np.where(mask, scores, -1.0)
        top_idx = np.argsort(-scores)[:top_k]
        return [self._meta_to_hit(self._metas[i], float(scores[i])) for i in top_idx if mask[i]]

    def _search_lexical(self, ...):  # 保留现有实现作为 fallback
        ...
```

**第三步：保留 lexical fallback**。embedding 文件不存在或 `sentence-transformers` 没装时自动退回。CI 不依赖 BGE 模型，生产模式可启用。

**第四步：测试同步**。`test_ugc_phase2.py` 走 lexical 路径（embedding 不存在），新增 `test_ugc_semantic.py` 跑 mock embedding 路径（注入 fake 模型）。

### 1.4 RepairAgent 是 regex 不是 agent（4 小时）

`_target_stop_index / _category_hint / _budget` 全靠正则。"把午餐那站改成更便宜的咖啡店"会丢"午餐"和"更便宜"两个信号。补 LLM 槽位抽取：

```python
# app/agent/specialists/repair_agent.py
class RepairAgent:
    def parse(self, message: str) -> FeedbackIntent:
        rule_result = self._rule_parse(message)
        if not get_settings().llm_api_key or not get_settings().agent_tool_calling_enabled:
            return rule_result
        prompt = self._build_prompt(message)
        llm_data = LlmClient().complete_json(
            prompt,
            fallback=rule_result.model_dump(),
            agent_name="repair_agent",
            system_prompt=(
                "你是路线反馈解析器。返回严格 JSON。"
                "不要编造未提及的字段，无法确定填 null。"
            ),
        )
        try:
            merged = {**rule_result.model_dump(), **{k: v for k, v in llm_data.items() if v is not None}}
            return FeedbackIntent.model_validate(merged)
        except ValidationError:
            return rule_result

    def _build_prompt(self, message: str) -> str:
        return f"""把用户的中文反馈拆成结构化 delta。

输出字段：
- event_type: REPLACE_POI | BUDGET_EXCEEDED | WEATHER_CHANGED | TIME_DELAYED | USER_REJECT_POI | USER_MODIFY_CONSTRAINT
- target_stop_index: 用户指明的站点序号（0-based），无法确定为 null
- category_hint: restaurant | cafe | nightlife | culture | scenic 或 null
- budget_per_person: 用户指明的新预算（人均），无法确定为 null
- deltas: 其他增量约束，无则空对象

规则：
- 复合反馈必须输出多个 delta（不要只挑一个）
- 模糊词归一化：午餐站 → target_stop_index 看上下文，无信息为 null
- "更便宜" → 不写 budget_per_person，写 deltas.budget_direction = "lower"
- 输出严格 JSON，不要 Markdown

反馈：{message}
"""
```

`_rule_parse` 是原本 `parse` 的内容改名。修补后规则路径仍可用，LLM 路径增量解析复合意图。

### 1.5 评估缺失（4 小时）

补一个端到端 eval 集合：

```python
# tests/test_agent_eval.py
from pathlib import Path
import json

from app.agent.conductor import Conductor
from app.agent.tools import get_tool_registry
from app.api.routes_agent import build_initial_state, AgentRunRequest
from app.llm.client import LlmClient

EVAL_CASES = [
    {
        "id": "case_quiet_friends_evening",
        "query": "晚上六点想和闺蜜聊聊，预算 150，少排队",
        "expected_themes": ["夜", "聊", "本地"],
        "expected_categories": {"restaurant"},
        "max_budget_violation_ratio": 0.2,
    },
    {
        "id": "case_rainy_indoor",
        "query": "下雨天，找个室内不无聊的，吃顿好的",
        "expected_themes": ["雨", "室内"],
        "expected_categories": {"restaurant"},
        "forbidden_categories": {"outdoor"},
    },
    {
        "id": "case_local_lunch_photos",
        "query": "中午想吃合肥本地菜，顺便能拍点照",
        "expected_themes": ["本地", "合肥"],
        "expected_categories": {"restaurant"},
    },
    # ... 至少 8 条
]


def run_one(case: dict):
    request = AgentRunRequest(
        user_id=f"eval_{case['id']}",
        free_text=case["query"],
        city="hefei",
        date="2026-05-08",
        time_window={"start": "12:00", "end": "20:00"},
        budget_per_person=200,
    )
    state = build_initial_state(request)
    return Conductor(get_tool_registry(), LlmClient()).run(state)


def evaluate(state, case):
    story = state.memory.story_plan
    if story is None:
        return False, "no_story_plan"
    text = f"{story.theme} {story.narrative}"
    has_theme = any(theme in text for theme in case["expected_themes"])
    stop_categories = {_cat(s.poi_id) for s in story.stops}
    has_required_categories = case["expected_categories"] <= stop_categories
    forbidden_hit = case.get("forbidden_categories", set()) & stop_categories
    grounded = all(s.ugc_quote_ref and s.ugc_quote for s in story.stops)
    ok = has_theme and has_required_categories and not forbidden_hit and grounded
    return ok, {
        "has_theme": has_theme,
        "categories_ok": has_required_categories,
        "forbidden_hit": list(forbidden_hit),
        "evidence_grounded": grounded,
    }


def test_agent_eval_pipeline_pass_rate():
    results = []
    passed = 0
    for case in EVAL_CASES:
        state = run_one(case)
        ok, detail = evaluate(state, case)
        results.append({"case": case["id"], "passed": ok, "detail": detail})
        if ok:
            passed += 1
    output = Path("data/eval/last_run.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nEval pass rate: {passed}/{len(EVAL_CASES)} = {passed / len(EVAL_CASES):.0%}")
    assert passed / len(EVAL_CASES) >= 0.7
```

CI 会输出 `data/eval/last_run.json`，每次提交可看到 pass-rate 变化，prompt 改动会触发回归。

---

## 二、三块加分项

### 2.1 AgentState + Trace 持久化到 SQLite（半天）

模块级 dict 重启就丢。复用现有 sqlite 基建：

```python
# app/agent/store.py
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from app.agent.state import AgentState

DB_PATH = Path("data/processed/agent_sessions.sqlite")
_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    phase TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON agent_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON agent_sessions(updated_at DESC);

CREATE TABLE IF NOT EXISTS agent_events (
    session_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    event_json TEXT NOT NULL,
    PRIMARY KEY (session_id, idx)
);
"""


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_SCHEMA)
    return conn


def save_state(state: AgentState) -> None:
    with _conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO agent_sessions
            (session_id, user_id, kind, phase, trace_id, state_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                state.goal.session_id,
                state.goal.user_id,
                state.goal.kind,
                state.phase,
                state.trace_id,
                state.model_dump_json(),
                datetime.utcnow().isoformat(),
            ),
        )


def load_state(session_id: str) -> AgentState | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT state_json FROM agent_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return AgentState.model_validate_json(row[0]) if row else None


def list_sessions(user_id: str, limit: int = 20) -> list[AgentState]:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT state_json FROM agent_sessions
            WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    return [AgentState.model_validate_json(row[0]) for row in rows]
```

配套写 `scripts/replay_trace.py`：

```python
import argparse
from app.agent.store import load_state

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_id")
    args = parser.parse_args()
    state = load_state(args.session_id)
    if state is None:
        print(f"No session: {args.session_id}")
        return
    print(f"Goal: {state.goal.kind} | {state.goal.raw_query}")
    print(f"Phase: {state.phase}")
    print(f"Steps ({len(state.steps)}):")
    for index, step in enumerate(state.steps, start=1):
        print(f"  [{index:>2}] {step.latency_ms:>5} ms | {step.tool_name:<25} | "
              f"{step.observation_summary}")
    if state.memory.critique:
        critique = state.memory.critique
        print(f"\nCritique: stop={critique.should_stop} | "
              f"theme={critique.theme_coherence} | evidence={critique.evidence_strength}")

if __name__ == "__main__":
    main()
```

`tests/test_agent_store.py` 验证 save → load → list 三个接口。

### 2.2 Conductor 并行调用（半天）

`recommend_pool` 和 `search_ugc_evidence` 逻辑独立，可并行执行：

```python
# app/agent/conductor.py
import asyncio

class Conductor:
    PARALLEL_PAIRS = [
        {"recommend_pool", "search_ugc_evidence"},
        # 未来可扩展更多并发集合
    ]

    async def run_async(self, state: AgentState) -> AgentState:
        reset_trace(state.goal.session_id)
        for _ in range(self.MAX_STEPS):
            decisions = await self._decide_batch(state)
            if not decisions or decisions[0].tool == "finish":
                state.phase = "DONE"
                return state
            results = await asyncio.gather(
                *(self._execute_async(state, d) for d in decisions),
                return_exceptions=True,
            )
            for decision, result in zip(decisions, results):
                if isinstance(result, Exception):
                    state.phase = "FAILED"
                    return state
                self._apply_result(state, result)
        state.phase = "FAILED"
        return state

    async def _decide_batch(self, state: AgentState) -> list[Decision]:
        first = self._decide(state)
        if first.tool == "finish":
            return [first]
        # 看 first.tool 是否能配对并行
        for pair in self.PARALLEL_PAIRS:
            if first.tool in pair:
                state_after = self._simulate_apply(state, first)
                second = self._decide(state_after)
                if second.tool in pair and second.tool != first.tool:
                    return [first, second]
        return [first]

    async def _execute_async(self, state: AgentState, decision: Decision) -> ToolResult:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self.tools.execute(decision.tool, state, decision.args)
        )
```

`routes_agent.run_agent` 改成 `await Conductor.run_async(...)`。测试 `test_conductor_parallel.py` 验证两个独立工具会被同时调度。

### 2.3 Prompt 文件化 + 回归集合（2 小时）

把散落在 specialist 代码里的 prompt 抽出来：

```
app/agent/prompts/
  story.system.md        # <!-- version: 1.0.0 -->
  story.eval.jsonl       # 6-8 条 (input, expected_keys)
  repair.system.md
  repair.eval.jsonl
  critic.system.md
  critic.eval.jsonl
```

`LlmClient` 拼接 system prompt 时记录版本号到 `ToolCall.observation_payload_ref`。

`tests/test_prompt_regression.py`：

```python
@pytest.mark.parametrize("prompt_name", ["story", "repair", "critic"])
def test_prompt_eval_set_schema_pass_rate(prompt_name, mock_llm_returning):
    cases = read_eval_set(prompt_name)
    passed = 0
    for case in cases:
        with mock_llm_returning(case["mock_response"]):
            result = invoke_specialist(prompt_name, case["input"])
            if all(key in result.model_dump() for key in case["expected_keys"]):
                passed += 1
    assert passed / len(cases) >= 0.95
```

---

## 三、四类收尾工程

### 3.1 README 重写

按"三屏可读"原则。第一屏放定位 + demo 动图 + 三个链接（在线 demo / 视频 / GitHub）；第二屏放架构图 + 技术栈；第三屏放 quick start + 验证命令。结构模板：

```markdown
# AIroute — Multi-Agent Local Route Planner

[在线 demo](...) · [Demo 视频](...) · [设计文档](docs/agent_development_plan.md)

<demo.gif>

基于 LLM tool calling 的本地路线规划 agent：
Conductor 主控 + 5 个 specialist + 9 个工具 + RAG over UGC + 幻觉检测 + 流式思考过程可视化。

## Architecture

<mermaid 图>

## Tech Stack

FastAPI · Pydantic · React · SQLite · BGE-small-zh embedding · DeepSeek/LongCat LLM · Amap API

## Quick Start

\```bash
pip install -e .[dev]
python scripts/embed_ugc.py            # 生成 UGC embedding (首次)
uvicorn app.main:app --port 8000       # 后端
cd frontend && pnpm install && pnpm dev # 前端
\```

打开 http://localhost:5173 → 收藏几张 UGC 卡片 → 现在出发。

## Verify

\```bash
curl localhost:8000/api/agent/tools | jq                  # 查看工具清单
curl -X POST localhost:8000/api/agent/run -d '{...}'      # 跑一次 agent
curl localhost:8000/api/agent/trace/{session_id} | jq     # 看 trace
python scripts/replay_trace.py {session_id}               # 命令行回放
pytest -v                                                 # 16+ tests
pytest tests/test_agent_eval.py                           # 端到端 eval
\```

## Design Decisions

详见 [docs/agent_development_plan.md](docs/agent_development_plan.md) 与
[docs/agent_finalization_plan.md](docs/agent_finalization_plan.md)。
```

### 3.2 Demo 视频脚本（60-90 秒）

按下面这条线录：

帧 1（10 秒）：UGC feed 页打开，光标快速滚动，收藏 4-5 张卡片（火锅、咖啡馆、夜市、本地菜），点"清零"演示一次状态重置，再收藏几张。

帧 2（10 秒）：点"现在出发"，右侧 `AgentThinkingPanel` 实时滚出 6-7 个工具调用，伴随中文标签（"在理解需求…在召回 UGC…在编排路线…"），每条带 latency 数字。

帧 3（15 秒）：地图渲染高德真实路线，标题用 `story_plan.theme`（如"庐州夏夜局"），副标用 `narrative`。点开 POI 列表，展开每个 stop 看 `why` + `ugc_quote`，画外音简短解释"每条 why 都引一条真实 UGC 原文"。

帧 4（15 秒）：在 feedback 框输入"第二站换近的火锅，预算到 250"，submit。Thinking panel 再次滚动（parse_feedback → replan_by_event → get_amap_chain → validate → critique）。地图重绘新 segment。

帧 5（10 秒）：终端窗口 `curl /api/agent/trace/{session_id} | jq` 滚出完整 trace JSON，展示每个 tool_name / args / observation_summary / latency_ms。再切到 `python scripts/replay_trace.py xxx` 命令行回放。

可以用 OBS 录屏，加字幕用 CapCut/剪映。视频长度控制在 75 秒上下。

### 3.3 部署

**后端**：Railway 或 Render（都有免费层）。`Procfile`：

```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

`requirements.txt` 增补 `sentence-transformers numpy`。Demo 用的 SQLite 数据文件（`hefei_pois.sqlite / ugc_hefei.jsonl / ugc_hefei_embeddings.npy / ugc_hefei_meta.jsonl`）直接 commit 进仓库（合计约 200MB，可启用 git lfs；若超限就把 embedding 改成首次启动时拉取）。环境变量：`LLM_API_KEY / LLM_PROVIDER / AMAP_WEB_SERVICE_KEY`。

**前端**：Vercel。`vercel.json` 把 `/api/*` 反代到后端域名。

**CORS**：`app/main.py` 的 `allow_origins` 加 Vercel 域名。

**冷启动延迟**：Render 免费层有 sleep，第一次访问 30 秒。简单方案是用 UptimeRobot 每 10 分钟 ping `/health`。

### 3.4 数据 / 文档配套

- `docs/agent_development_plan.md`：原方案，保留作为完整设计文档。
- `docs/agent_finalization_plan.md`：本文件，收尾开发清单。
- `docs/agent_architecture.md`：新写一份 1500 字的架构说明，含 Mermaid 流程图。
- `data/processed/README.md` 更新：列出 sqlite / jsonl / npy / meta 四个文件的作用和生成方式。
- `scripts/README.md`：列出三个脚本（`import_hefei_pois.py / embed_ugc.py / replay_trace.py`）的用法。

---

## 四、时间表

按"必修 → 加分 → 收尾"三段切，5-7 天可闭环。

**Day 1**（必修 1.1 + 1.4 + 1.5）：

- 加 `/api/agent/tools` 端点（10 分钟）
- `RepairAgent` 加 LLM 槽位抽取路径（4 小时）
- 写 `tests/test_agent_eval.py`，跑通 8 条 eval case（4 小时）
- 跑全部测试，确保 16+8 全绿

**Day 2**（必修 1.3 上半）：

- 写 `scripts/embed_ugc.py`，跑一次离线生成 embedding 文件
- 改造 `UgcVectorRepo._search_semantic` + 保留 lexical fallback
- 跑 `test_ugc_phase2.py` 验证 fallback 路径

**Day 3**（必修 1.2 + 1.3 下半）：

- `stream_trace` 改 async 真流式（asyncio.Queue）
- 前端 `AgentThinkingPanel` 接 EventSource
- 补 `test_ugc_semantic.py` 验证 embedding 路径
- 集成测试：完整 agent 跑一次，看前端能否实时收事件

**Day 4**（加分 2.1 + 2.2）：

- AgentState + trace 持久化到 sqlite
- 写 `scripts/replay_trace.py`
- Conductor 并行调用（可选，时间紧可推到 Day 7）

**Day 5**（加分 2.3 + 文档）：

- prompt 文件化，三个 specialist 各拆出一份 .system.md
- 写 `tests/test_prompt_regression.py`
- 重写 README 三屏结构
- 写 `docs/agent_architecture.md`

**Day 6**（收尾工程 3.2 + 3.3）：

- 录 demo 视频（OBS + CapCut，60-90 秒）
- 后端部署到 Railway，前端部署到 Vercel
- 配置 UptimeRobot 防止 sleep
- 在线 demo 完整跑一遍，修任何线上 bug

**Day 7**（缓冲 + 复盘）：

- 修任何 Day 1-6 的遗留 bug
- 跑一次完整端到端，从 README 命令到 demo 视频每一步复现
- 如果时间富余，做 Conductor 并行调用（2.2）

---

## 五、验收清单

每一阶段交付时按下面这张表自检：

| 项 | 验收标准 | 验证命令 |
|---|---|---|
| 端点完整 | `/api/agent/{run,adjust,trace,stream,tools}` 全部 200 | `curl /api/agent/tools` |
| LLM 流式 | EventSource 能在 agent 运行中收到增量事件 | 浏览器 DevTools Network 看 SSE |
| Embedding | `data/processed/ugc_hefei_embeddings.npy` 存在且形状 (N, 512) | `python -c "import numpy as np; print(np.load('...').shape)"` |
| 语义检索 | query="安静咖啡"返回 cafe 类 UGC 占 top 50% | `pytest tests/test_ugc_semantic.py` |
| 复合反馈 | "第二站换近的火锅，预算到 250" 同时改 stop + budget | `pytest tests/test_agent_stage4.py` |
| 幻觉检测 | 注入坏 LLM 回复，post_check 报告 hallucinated_poi/ugc | `pytest tests/test_agent_stage3.py::test_story_agent_post_check_rejects_hallucinated_poi_and_quote` |
| 评估通过率 | 8 条 eval case ≥ 70% 通过 | `pytest tests/test_agent_eval.py` |
| 持久化 | save_state → restart → load_state 一致 | `pytest tests/test_agent_store.py` |
| Replay | `python scripts/replay_trace.py {id}` 输出完整 trace | 人肉看输出 |
| 部署 | 在线 demo 访问 `/api/health` 返回 200 | `curl https://xxx/api/health` |

---

## 六、风险与回避

- **BGE 模型下载慢**：第一次跑 `embed_ugc.py` 会从 HuggingFace 拉 100MB 模型。国内网络走镜像：`HF_ENDPOINT=https://hf-mirror.com python scripts/embed_ugc.py`，或下载后放 `~/.cache/huggingface/` 离线复用。
- **embedding 文件体积**：6000 条 × 512 维 × float32 = 12MB，commit 进仓库可以。如果未来 UGC 涨到 5 万条，改成构建时下载或挂 git lfs。
- **Amap 配额**：免费 key 日 5000 次，feedback 频繁调整会爆。短期：开发环境用 `FakeRouteClient` mock；长期：按 `(origin, dest, mode)` LRU 缓存（半天工作量）。
- **LLM 失败时 demo 翻车**：录 demo 视频前必须连 LLM 完整跑一遍；部署时确保 `agent_tool_calling_enabled=true` 时 fallback 仍能在 LLM 抛错时接住。
- **SSE 与反向代理**：Render/Vercel 默认会 buffer SSE 流。后端 response header 加 `X-Accel-Buffering: no`、`Cache-Control: no-cache`，确保流式推送不被缓冲。
- **Render 免费层 sleep**：用 UptimeRobot 每 10 分钟 ping `/health`，或迁到 Railway / Fly.io（Always-on 免费层）。
- **测试与生产数据偏差**：`test_agent_stage3.py` 和 `test_agent_stage4.py` 用 `city="shanghai"` 走 seed 兜底，生产用 hefei。统一改成 hefei 或单独建 `conftest` fixture 注入 mock。
- **conftest 强制关 LLM**：所有现有测试都走规则路径。新增 `tests/test_agent_with_llm.py` 用 mock LlmClient 测 LLM 启用的路径，避免上线后才发现 LLM 路径有 bug。

---

## 七、最终交付清单

代码：

- `app/agent/` 完整（新增/修改）：conductor / state / tools / tool_schemas / store（sqlite）/ tracing（asyncio queue）/ story_models / specialists/* / prompts/*
- `app/repositories/ugc_vector_repo.py`：BGE + lexical 双轨
- `app/api/routes_agent.py`：新增 `/tools` 端点，改造 `/run` 异步、`/stream` 真流式
- `scripts/embed_ugc.py`、`scripts/replay_trace.py`、`scripts/import_hefei_pois.py`（已有）

数据：

- `data/processed/hefei_pois.sqlite`（已有）
- `data/processed/ugc_hefei.jsonl`（已有）
- `data/processed/ugc_hefei_embeddings.npy`（新增）
- `data/processed/ugc_hefei_meta.jsonl`（新增）
- `data/processed/agent_sessions.sqlite`（运行时产生）
- `data/eval/last_run.json`（CI 产出）

测试：

- 现有 16 个测试全绿
- 新增 `test_agent_eval.py`（8 条 eval）、`test_agent_store.py`、`test_ugc_semantic.py`、`test_prompt_regression.py`、`test_conductor_parallel.py`（如做 2.2）

文档：

- `README.md`（重写，三屏结构）
- `docs/agent_development_plan.md`（原方案保留）
- `docs/agent_finalization_plan.md`（本文件）
- `docs/agent_architecture.md`（新写）
- `data/processed/README.md`、`scripts/README.md`（更新）

部署：

- 后端在线（Railway / Render）+ 前端在线（Vercel）
- demo 视频（60-90 秒）

---

## 八、收尾原则

按以下三条优先级排序解决冲突：

第一，**Day 1 五件必修先做完再做别的**。这五件是基线，否则当前测试都跑不全。

第二，**1.3（BGE embedding）和 1.2（真流式）是分水岭**。修完之前项目只能叫"基于 LLM 的多工具系统"，修完之后才能叫"agent + RAG"。

第三，**部署与文档不要拖到最后一天**。Day 6 留出整天专门做这件事，因为部署经常碰到环境问题，临时排查会拖崩节奏。

5-7 天后，整个 AIroute agent 项目从代码到数据到文档到在线 demo 一次性闭环。

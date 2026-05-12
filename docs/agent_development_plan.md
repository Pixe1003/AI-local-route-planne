# AIroute Agent 化详细开发方案

> 目标：把"根据 UGC 串联多个 POI 的 agent"这一赛题命题真正落到代码——让 LLM 在做决策（选工具、串故事、审稿、应对反馈），让规则代码退到工具内部做兜底。
>
> 假设：时间充足，以 agent 的设计与应用为核心，建立在团队已完成的"合肥 POI 真数据接入 + 主链路 UGC→Pool→Route Chain"之上。

---

## 零、总体架构与判断

现状的代码资产可以全部保留，包括 `PoolService` 的打分、`AmapRouteClient`、`PreferenceSnapshot`、`SKILL.md` 加载机制、`RouteValidator/Repairer/Replanner` 三件套、以及合肥 SQLite POI 数据。要改的是这些资产被**调度**的方式——把"FastAPI 路由直接调 service"换成"FastAPI 路由把请求交给 AgentLoop，AgentLoop 决定调哪个 service、调几次、什么时候停"。

整体形态采用 **主控 Agent + 多专家 Agent + 工具层** 三层：

- **主控（Conductor）**：理解目标、规划步骤、调用专家、判断终止。
- **专家（Specialist）**：意图专家（NeedAgent）、推荐专家（PoolAgent）、串联专家（StoryAgent）、修复专家（RepairAgent）、审稿专家（Critic）。
- **工具层（Tool Registry）**：把现有 services 包成 `Tool`，每个 tool 有 JSON schema、handler、降级行为、超时、缓存策略。

Conductor 用 LLM tool calling 协议在 schema 列表里挑工具，专家内部各自有自己的 prompt 上下文。Demo 时把 Conductor 的每一步轨迹流式回给前端，做出"agent 在思考"的视觉效果。

这种"多 agent + 工具"的形态既符合赛题对 agent 的字面要求（LLM 真的在做决策），又能复用已有规则代码（落到工具内部）。

---

## 一、目录结构与新增模块

保留现有 `app/` 不变，新增 `app/agent/` 子包作为所有 agent 化代码的入口。老 services 退化成 agent 调用的工具，不再被 routes 直接调用（除高德 `route_chain` 这条对延迟敏感的链路）。

```
backend/app/
  agent/
    __init__.py
    conductor.py            # 主控 AgentLoop + 终止策略
    state.py                # AgentState、AgentStep、AgentMemory
    tools.py                # 工具注册表
    tool_schemas.py         # 每个工具的 JSON Schema
    specialists/
      need_agent.py         # 意图解析专家
      pool_agent.py         # 候选池专家
      story_agent.py        # 故事化串联专家
      repair_agent.py       # 反馈/重规划专家
      critic.py             # 路线审稿专家
    prompts/
      conductor.system.md
      need.system.md
      story.system.md
      critic.system.md
      repair.system.md
    tracing.py              # 把每步事件流出到前端
    cache.py                # AgentResult + Amap segment 缓存
    policies.py             # 终止条件 / 步数上限 / 预算控制
    store.py                # AgentState 持久化
  api/
    routes_agent.py         # /api/agent/run + /api/agent/stream + /api/agent/trace + /api/agent/adjust
```

不动现有 `services/`，只新增 `agent/`。

---

## 二、状态模型（State 是 Agent 的灵魂）

`AgentState` 是这套系统真正的"记忆"。它必须把上一轮所有发现物都装进去，让 Conductor 决策时知道"已经做过什么、还差什么"。

```python
# app/agent/state.py
class AgentGoal(BaseModel):
    kind: Literal["plan_route", "adjust_route", "explain_route", "explore_more"]
    raw_query: str
    session_id: str
    user_id: str
    locale_city: str = "hefei"

class ToolCall(BaseModel):
    tool_name: str
    args: dict
    started_at: datetime
    ended_at: datetime | None = None
    observation_summary: str | None = None      # 给 LLM 看的摘要
    observation_payload_ref: str | None = None  # 完整 payload 落到 memory 里
    error: str | None = None
    latency_ms: int = 0
    tokens_used: int = 0

class Critique(BaseModel):
    theme_coherence: int
    evidence_strength: int
    pacing: int
    preference_fit: int
    narrative: int
    should_stop: bool
    hint: str | None = None
    issues: list[str] = []

class AgentMemory(BaseModel):
    """大对象按 ref 存进来，避免每步 prompt 都把 KB 级 payload 塞进去"""
    pool: PoolResponse | None = None
    intent: StructuredIntent | None = None
    candidates: list[PoiWithEvidence] = []
    story_plan: StoryPlan | None = None
    route_chain: RouteChainResponse | None = None
    validation: ValidationResult | None = None
    critique: Critique | None = None
    ugc_hits: list[UgcHit] = []

class AgentState(BaseModel):
    goal: AgentGoal
    profile: UserNeedProfile
    preference: PreferenceSnapshot | None = None
    context: PlanContext
    steps: list[ToolCall] = []
    memory: AgentMemory = Field(default_factory=AgentMemory)
    phase: Literal["UNDERSTANDING","RETRIEVING","COMPOSING","CHECKING","PRESENTING","DONE","FAILED"] = "UNDERSTANDING"
    version: int = 1
    trace_id: str = Field(default_factory=lambda: uuid4().hex)
```

`AgentMemory` 用引用而非内嵌大 payload，因为 LLM tool calling 时每一轮上下文都要带；如果把 24 个 POI + UGC 全塞进去，token 会爆。摘要 + ref 的设计参考了 OpenAI 官方文档对长上下文 agent 的推荐。

存储用 sqlite (`data/processed/agent_state.sqlite`) 或 Redis。前期内存 dict + pickle 落盘也能跑通 demo。新增 `app/agent/store.py`：

```python
def save_state(state: AgentState) -> None: ...
def load_state(session_id: str) -> AgentState | None: ...
def list_sessions(user_id: str, limit: int = 20) -> list[AgentState]: ...
```

---

## 三、工具注册表

工具是规则代码的门面。每个工具有四件配套：name、schema、handler、fallback。

```python
# app/agent/tool_schemas.py
PARSE_INTENT = {
    "name": "parse_intent",
    "description": "从自由文本+上下文中抽取硬约束(start_time/end_time/budget)和软偏好(pace/avoid_queue/photography_priority/food_diversity/avoid_pois)。",
    "parameters": {
        "type": "object",
        "properties": {
            "free_text": {"type": "string"},
            "selected_poi_ids": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["free_text"]
    }
}

SEARCH_UGC = {
    "name": "search_ugc_evidence",
    "description": "按主题/动线/人群/时段从 UGC 语料库召回片段。返回带 POI id 的 quote 列表。",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "filters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "array", "items": {"type": "string"}},
                    "time_slot": {"type": "string"},
                    "party_fit": {"type": "string"}
                }
            },
            "top_k": {"type": "integer", "default": 12}
        },
        "required": ["query"]
    }
}

RECOMMEND_POOL = {...}     # 包装 PoolService
COMPOSE_STORY = {...}      # 调 StoryAgent
GET_AMAP_CHAIN = {...}     # 包装 routes_route.build_route_chain
VALIDATE_ROUTE = {...}     # 包装 RouteValidator
REPAIR_ROUTE = {...}       # 包装 RouteRepairer
REPLAN_BY_EVENT = {...}    # 包装 RouteReplanner
EXPLAIN_STOP = {...}       # 给单站生成 why_this_one + 引 UGC
FINISH = {"name": "finish", "description": "Agent 任务完成。返回最终路线和总结。", "parameters": {...}}
```

```python
# app/agent/tools.py
@dataclass
class Tool:
    name: str
    schema: dict
    handler: Callable[[AgentState, dict], ToolResult]
    cache_key_fn: Callable[[dict], str] | None = None
    fallback: Callable[[AgentState, dict], ToolResult] | None = None
    timeout_s: float = 10.0

class ToolRegistry:
    def schemas_for_llm(self) -> list[dict]: ...
    def execute(self, name: str, state: AgentState, args: dict) -> ToolResult: ...
```

每个 handler 是无状态的：拿到 state 和 args，返回 `ToolResult(observation_summary, payload, memory_patch)`。`memory_patch` 决定写回 AgentMemory 的哪些字段。这是 Conductor 不直接操作 AgentMemory 的关键——所有副作用都从 handler 流出，trace 可追溯。

---

## 四、Conductor 主循环

```python
# app/agent/conductor.py
class Conductor:
    MAX_STEPS = 8
    MAX_TOKENS = 6000
    MAX_LATENCY_MS = 30_000

    def __init__(self, tools: ToolRegistry, llm: LlmClient):
        self.tools = tools
        self.llm = llm

    def run(self, state: AgentState, stream: Callable[[AgentEvent], None] = None) -> AgentState:
        stream = stream or (lambda evt: None)
        stream(AgentEvent(type="started", state=state.snapshot()))
        for step_index in range(self.MAX_STEPS):
            decision = self._decide(state)
            stream(AgentEvent(type="decided", decision=decision))
            if decision.tool == "finish":
                state.phase = "DONE"
                stream(AgentEvent(type="finished", state=state.snapshot()))
                return state
            result = self.tools.execute(decision.tool, state, decision.args)
            self._apply_result(state, decision, result)
            stream(AgentEvent(type="observed", result=result))
            if self._should_stop_for_budget(state):
                state.phase = "FAILED"
                stream(AgentEvent(type="aborted", reason="budget_exceeded"))
                return state
        state.phase = "FAILED"
        return state

    def _decide(self, state: AgentState) -> Decision:
        prompt = self._build_decision_prompt(state)
        return self.llm.complete_tool_call(
            prompt,
            tools=self.tools.schemas_for_llm(),
            fallback=self._rule_based_decision(state),
        )
```

三个关键设计：

**Decision 总是落到工具调用**。Conductor 不输出自然语言"我觉得应该……"，而是输出一个 tool call。这把所有 agent 推理沉淀成可追溯的 tool 调用序列。

**`_rule_based_decision` 兜底**。当 LLM key 没配、超时、返回坏格式时，按 phase 走预设序列：
`UNDERSTANDING → parse_intent → RETRIEVING → recommend_pool + search_ugc_evidence → COMPOSING → compose_story → CHECKING → get_amap_chain + validate_route → 必要时 repair_route → finish`。
这套规则序列等价于现有 services 的执行顺序，保证 LLM 不在也能跑 demo。

**Stream callback**。`AgentEvent` 包含 `decided / observed / finished / aborted` 四类事件，每个事件带轻量摘要，前端 SSE 订阅做"agent 思考过程"展示。

---

## 五、四位专家 Agent

工具的 handler 内部各调一个专家 agent。工具是接口，专家是工具内部的 LLM 推理。

### 5.1 NeedAgent（意图解析专家）

替代现有 `IntentService._enhance_intent_with_llm`。改造点：

- 提示词加入"槽位抽取"思维，返回"已确定 / 待澄清"的 slot 列表
- 支持"用户输入有歧义时返回 `needs_clarification: true`"
- 复合意图（"换近一点的火锅，预算调到 250"）输出多个 slot delta，而不是单 event_type

```python
# app/agent/specialists/need_agent.py
class NeedAgent:
    def parse(self, text: str, context: PlanContext, prior: StructuredIntent | None) -> ParsedIntent:
        prompt = self._build_prompt(text, context, prior)
        result = self.llm.complete_json(prompt, fallback=self._rule_fallback(text, context))
        return self._merge_with_prior(result, prior)
```

提示词（`prompts/need.system.md`）：

```
你是本地路线 Agent 的需求理解专家。

任务：把用户的中文自由文本解析为结构化意图，覆盖以下槽位：
- hard.start_time / hard.end_time / hard.budget_total / hard.must_include_meal
- soft.pace (relaxed/balanced/efficient)
- soft.avoid_queue / soft.weather_sensitive / soft.photography_priority / soft.food_diversity
- soft.party_type (couple/friends/family/solo/senior)
- soft.themes: 主题数组，取值从 [本地菜, 拍照, 文艺, 夜景, citywalk, 雨天室内, 省钱, 慢节奏, 高效]
- delta: 相对 prior 的变更（增量解析时用）。例如 {"budget_total": 250, "replace_stop_index": 1, "category_hint": "cafe"}
- avoid_pois / must_visit_pois

规则：
1. 槽位无法确定就返回 null，不要编造。
2. 复合意图必须拆成多个 delta。
3. 输出严格 JSON，不要 Markdown。
4. 已有上下文(prior)字段未被显式覆盖时保留。
```

### 5.2 PoolAgent（候选池专家）

包装现有 `PoolService.generate_pool`，但增加两个 agent 化能力。

**第一，类别映射在 PoolAgent 内做**。合肥 SQLite 全是 `category="restaurant"`，PoolAgent 内部读 `poi.sub_category` 做映射：

```python
class PoolAgent:
    SUB_CATEGORY_MAPPING = {
        "咖啡厅": "cafe", "茶艺馆": "cafe", "甜品店": "cafe", "糕饼店": "cafe", "冷饮店": "cafe",
        "火锅店": "restaurant", "综合酒楼": "restaurant", "海鲜餐厅": "restaurant",
        "酒吧": "nightlife", "夜总会": "nightlife",
        "快餐厅": "restaurant", "外国餐厅": "restaurant",
        # ... 兜底 fall through 到 restaurant
    }

    def derive_category(self, poi: PoiDetail) -> str:
        sub = poi.sub_category or ""
        for key, mapped in self.SUB_CATEGORY_MAPPING.items():
            if key in sub:
                return mapped
        return poi.category
```

放在 PoolAgent 而不是 import 脚本里，好处是不需要重跑 import、可以即时调整映射规则。

**第二，召回 + 重排两阶段**。第一阶段用 `PoiScoringService` 出 top 40；第二阶段调 `search_ugc_evidence` 给每个 top POI 附 2-3 条 UGC 片段，作为 LLM 重排的 evidence。重排提示词让 LLM 在"评分高 vs UGC 强信号"之间做权衡，输出最终 24 个候选 + reason。

### 5.3 StoryAgent（故事化串联专家）——赛题命门

新的核心模块。职责：拿候选 POI（含 UGC 摘要）+ intent + preference → 输出"有主题的 POI 序列 + 每站 why + dropped 原因"。

```python
class StoryPlan(BaseModel):
    theme: str                         # 例如 "庐州本帮味·城东漫游"
    narrative: str                     # 总叙述 60-100 字
    stops: list[StoryStop]
    dropped: list[DroppedPoi]
    fallback_used: bool = False

class StoryStop(BaseModel):
    poi_id: str
    role: Literal["opener","midway","main","rest","closer"]
    why: str                           # 引用 1 条 UGC 原文
    ugc_quote_ref: str                 # post_id, 让前端可点开看原文
    suggested_dwell_min: int

class StoryAgent:
    MAX_RETRY = 2

    def plan(self, candidates: list[PoiWithUgc], state: AgentState) -> StoryPlan:
        for attempt in range(self.MAX_RETRY + 1):
            raw = self.llm.complete_json(
                self._build_prompt(candidates, state, last_issues=...),
                fallback=self._fallback_plan(candidates, state),
                agent_name="story_planner",
            )
            plan = StoryPlan.model_validate(raw)
            issues = self._post_check(plan, candidates, state)
            if not issues:
                return plan
        return self._fallback_plan(candidates, state)
```

提示词（`prompts/story.system.md`）：

```
你是本地 citywalk Agent 的"路线编剧"。

任务：给用户编一条 3-5 站、带主题的合肥半日路线。每站要有清晰的角色
（opener/midway/main/rest/closer），并引用 UGC 原文做证据。

约束：
- 必须包含 1 家餐饮（restaurant 类），可选 1 个 cafe 类作为休息节点。
- 总时长不超过用户时间窗。预算超 20% 以内可接受。
- 用户必去 POI（must_visit）必须全部包含。
- 用户排除 POI（avoid）必须排除。
- 不允许编造 POI；只能用候选清单里出现的 POI。
- 不允许编造 UGC 原文；只能引用候选 POI 自带的 quote 列表。

候选 POI（带 UGC 摘要）：
{poi_list_block}

用户上下文：
- 时间窗：{start}-{end}
- 预算/人：{budget}
- 人群：{party_type}
- 主题：{themes}
- 已收藏偏好：{liked_count} 个 POI，类目权重：{category_weights}
- 已确认的硬约束：{hard_constraints}

输出严格 JSON：
{
  "theme": "8-12 字的主题",
  "narrative": "60-100 字的总叙述",
  "stops": [{
    "poi_id": "...",
    "role": "opener|midway|main|rest|closer",
    "why": "30-50 字，必须自然嵌入一句 UGC 原文",
    "ugc_quote_ref": "post_id 字符串",
    "suggested_dwell_min": 整数
  }],
  "dropped": [{"poi_id": "...", "reason": "..."}]
}
```

`_post_check` 做硬验证（幻觉检测是关键）：

```python
def _post_check(self, plan: StoryPlan, candidates, state) -> list[str]:
    issues = []
    poi_set = {p.poi_id for p in plan.stops}
    candidate_ids = {p.poi_id for p in candidates}
    if poi_set - candidate_ids:
        issues.append("hallucinated_poi")
    missing_must = set(state.intent.must_visit_pois) - poi_set
    if missing_must:
        issues.append(f"missing_must_visit:{missing_must}")
    categories = {self._cat(p.poi_id) for p in plan.stops}
    if "restaurant" not in categories:
        issues.append("no_restaurant")
    if len(plan.stops) < 3 or len(plan.stops) > 6:
        issues.append("bad_stop_count")
    for stop in plan.stops:
        if not self._quote_exists(stop.ugc_quote_ref, candidates):
            issues.append(f"hallucinated_quote:{stop.ugc_quote_ref}")
    return issues
```

LLM 编 POI 或编 UGC 原文是这类系统最大的失分点，post-check 一旦发现就再调一次 LLM（带 issue hint），最多 2 次后回到规则 fallback。

### 5.4 RepairAgent（反馈/重规划专家）

复用现有 `RouteReplanner` 的 5 种 event handler，但把上层的 event 分类从关键词扫描换成 LLM 槽位抽取：

```python
class RepairAgent:
    def parse_feedback(self, message: str, state: AgentState) -> list[FeedbackEvent]:
        # LLM 抽取，输出可能是多个 event：
        # [{"type":"REPLACE","target":1,"hint":"近一点的火锅"},
        #  {"type":"MODIFY","field":"budget","value":250}]
        ...

    def apply(self, events: list[FeedbackEvent], state: AgentState) -> StoryPlan:
        # 串行应用，每个 event 触发对应的 RouteReplanner 方法
        ...
```

### 5.5 Critic（审稿专家）

```python
class Critic:
    def review(self, plan: StoryPlan, validation: ValidationResult, state: AgentState) -> Critique:
        prompt = self._build_prompt(plan, validation, state)
        return self.llm.complete_json(prompt, fallback=self._rule_critique(plan, validation))
```

Critic 不修改 plan，只输出评分和建议。Conductor 看到 `should_stop=False` 就再调一次 StoryAgent（带 `critique.hint` 作为新约束）。这是 paper-insights 第 7 条"validate before explaining"的强化版——validate 是规则校验，critic 是模型审稿，两个串联。

---

## 六、UGC 子系统升级（赛题命门）

独立于 agent 主线，建议并行推进。目标是让 UGC 不再是装饰。

### 6.1 UGC 数据结构

新增 `data/processed/ugc_hefei.jsonl`，每行一个 UGC 片段：

```json
{
  "post_id": "ugc_hf_000123",
  "poi_id": "hf_poi_000045",
  "source": "xiaohongshu",
  "author": "合肥探店姑娘",
  "text": "三孝口这家老火锅，毛肚和黄喉都是当天送的。晚上 6 点前不用等位，靠包间那一桌讲话声音小一点。",
  "topic": ["火锅", "本地味", "工作日晚餐"],
  "vibe": ["热闹", "市井"],
  "time_slot": ["weekday_evening"],
  "party_fit": ["friends", "family"],
  "story_role": ["main", "closer"],
  "sentiment": 0.85,
  "created_at": "2025-09-12"
}
```

数据来源三选一：

1. 真实爬取（合规风险高，赛题语境可能不允许）；
2. 用合肥本地 POI + 子类目 + 商圈，让 LLM 离线生成 5-10 条仿写 UGC（可控、合规、风格多样）；
3. 混合，少量真实 + 多数仿写。

建议走 2，写 `scripts/synthesize_ugc.py` 离线批量生成：

```python
def synthesize_for_poi(poi: PoiDetail, count: int = 6) -> list[UgcPost]:
    """对每个 POI 用 LLM 生成 6 条不同风格/角色的 UGC"""
    prompt = f"""
    给合肥的 POI 生成 {count} 条不同风格的仿真用户点评。
    POI 名: {poi.name}, 子类目: {poi.sub_category}, 商圈: {poi.business_area}, 评分: {poi.rating}
    要求：
    - 每条 30-80 字，口语化，混杂方言/网络梗
    - 标注 topic/vibe/time_slot/party_fit/story_role
    - 风格分布：3 条正面、2 条中立、1 条略带吐槽
    - source 在 xiaohongshu/dianping/meituan 间分布
    输出 JSON 数组，每条 schema 与 UgcPost 一致。
    """
    return llm.complete_json_array(prompt, ...)
```

跑一次离线，生成约 6000 条 UGC（1000 POI × 6 条），耗时几小时，成本可控。

### 6.2 UGC 向量索引

新增 `app/repositories/ugc_vector_repo.py`：

```python
import chromadb
from sentence_transformers import SentenceTransformer

class UgcVectorRepo:
    EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"  # 512 维, 中文友好

    def __init__(self):
        self.model = SentenceTransformer(self.EMBEDDING_MODEL)
        self.client = chromadb.PersistentClient(path="data/processed/chroma")
        self.col = self.client.get_or_create_collection("ugc_hefei")

    def index_all(self, posts: list[UgcPost]) -> None:
        ...

    def search(self, query: str, filters: dict | None = None, top_k: int = 12) -> list[UgcHit]:
        emb = self.model.encode(query, normalize_embeddings=True).tolist()
        where_clause = self._build_where(filters)
        results = self.col.query(
            query_embeddings=[emb],
            n_results=top_k,
            where=where_clause
        )
        return [self._to_hit(r) for r in results]

    def neighbors_for_poi(self, poi_id: str, top_k: int = 6) -> list[UgcHit]:
        ...
```

把现有 `VectorRepository` 标记 deprecated 但保留，确保无 embedding 时也能跑（fallback 到旧的关键词匹配）。

### 6.3 UGC 进入打分

`PoiScoringService._ugc_match_score` 改造：

```python
def _ugc_match_score(self, poi, text: str) -> float:
    if not text:
        return 6.0
    hits = self.ugc_vector_repo.neighbors_for_poi(poi.id, top_k=4)
    if not hits:
        return 6.0
    query_emb = self.ugc_vector_repo.embed(text)
    similarities = [cosine(query_emb, hit.embedding) for hit in hits]
    avg = sum(similarities) / len(similarities)
    return min(6.0 + avg * 12.0, 18.0)  # 6-18 区间
```

这一步让 `ScoreBreakdown.ugc_match` 从硬编码 6 个关键词变成真语义匹配。

### 6.4 UGC 进入解释链

`StoryAgent` 的 prompt 里，每个候选 POI 都附 2-3 条最相关 UGC，让 LLM 在 `why` 字段引用其中一条。`RefinedStop.ugc_evidence` 字段填这条被引用的 UGC（带 post_id + source）。前端 `AmapRoutePage` 的"路线点位"列表里每个 POI 展开后能看到原文 + 来源。

---

## 七、合肥数据修复

不要重跑 `import_hefei_pois.py`。改在 PoolAgent 内做映射，保持 SQLite 不动。但可加一个可选的二次脚本作为永久修复：

```python
# scripts/refine_hefei_categories.py
"""根据 sub_category 给 pois 表加一个派生列 derived_category"""
def refine():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("ALTER TABLE pois ADD COLUMN derived_category TEXT")
        for row in conn.execute("SELECT id, sub_category FROM pois"):
            derived = derive_category(row["sub_category"])
            conn.execute("UPDATE pois SET derived_category = ? WHERE id = ?", (derived, row["id"]))
        # 更新 app_pois 视图，让 category 字段返回 derived_category
        conn.execute("DROP VIEW app_pois")
        conn.execute("""CREATE VIEW app_pois AS SELECT
            id, name, city, derived_category AS category, sub_category, ...""")
```

这样 PoolService 不改一行代码，候选池自然会分出 cafe / nightlife / restaurant 多个类别，category 约束就能满足。

---

## 八、API 层与前端

### 8.1 新增 routes_agent.py

```python
# app/api/routes_agent.py
router = APIRouter(prefix="/agent", tags=["agent"])

class AgentRunRequest(BaseModel):
    user_id: str
    free_text: str
    city: str = "hefei"
    time_window: TimeWindow
    date: str
    budget_per_person: int | None = None
    preference_snapshot: PreferenceSnapshot | None = None
    session_id: str | None = None
    parent_session_id: str | None = None    # for "adjust" goal

@router.post("/run")
async def run(req: AgentRunRequest):
    state = build_initial_state(req)
    conductor = Conductor(tools=get_tool_registry(), llm=LlmClient())
    final = conductor.run(state)
    save_state(final)
    return AgentRunResponse(...)

@router.get("/stream/{session_id}")
async def stream(session_id: str):
    """SSE: 把 Conductor 的事件流推给前端，做思考过程展示"""
    async def event_gen():
        async for event in get_event_bus(session_id).subscribe():
            yield f"data: {event.json()}\n\n"
    return StreamingResponse(event_gen(), media_type="text/event-stream")

@router.get("/trace/{session_id}")
def trace(session_id: str) -> AgentTrace:
    state = load_state(session_id)
    return AgentTrace(steps=state.steps, phase=state.phase, ...)

@router.post("/adjust")
async def adjust(req: AdjustRequest):
    """复用主控，goal.kind = adjust_route"""
    parent = load_state(req.parent_session_id)
    state = build_adjust_state(parent, req)
    final = Conductor(...).run(state)
    return ...
```

### 8.2 前端改造

`AmapRoutePage` 加 "Agent 思考过程"侧边抽屉，订阅 `/api/agent/stream/{session_id}` 的 SSE：

```tsx
function AgentThinkingPanel({ sessionId }: { sessionId: string }) {
  const [events, setEvents] = useState<AgentEvent[]>([])
  useEffect(() => {
    const source = new EventSource(`/api/agent/stream/${sessionId}`)
    source.onmessage = e => setEvents(prev => [...prev, JSON.parse(e.data)])
    return () => source.close()
  }, [sessionId])
  return (
    <aside className="thinking-panel">
      {events.map((e, i) => <ThinkingStep key={i} event={e} />)}
    </aside>
  )
}
```

每个 `ThinkingStep` 渲染成一行可点开的卡片，标题用工具名映射（"在抽取意图..." / "在搜索 UGC..." / "在编排路线..."），点开看 args 和 observation_summary。这是 demo 最有效的视觉杀招。

`AmapRoutePage` 的标题从 POI 名拼接改为 `state.memory.story_plan.theme`，副标题用 `state.memory.story_plan.narrative`。每个 POI 卡片下方展开能看到 `why_this_one` 引用的 UGC 原文（带 post_id 可看 source 跳转）。

### 8.3 主流程切换

`DiscoveryFeedPage.submit` 现在调 `/api/pool/generate` + `/api/route/chain`。改成调 `/api/agent/run`，agent 内部决定调哪些工具，结果包含 ordered POI ids、AmapRouteChain、StoryPlan。`AmapRoutePage` 通过 `session_id` 拉数据和订阅事件流。

旧的 `routes_pool / routes_plan / routes_chat` 保留但标 "compatibility"，README 写明 primary flow 是 `/api/agent/*`。

---

## 九、阶段性里程碑

按"每个阶段都能独立 demo"的原则切。每个阶段 2-3 天，总共 4-5 个阶段、10-13 天。

### 阶段 1：骨架立起来（2 天）

交付物：

- `app/agent/state.py`、`tools.py`、`tool_schemas.py`、`conductor.py` 骨架
- 工具 `parse_intent / recommend_pool / get_amap_chain` 三件先包装好
- `LlmClient.complete_tool_call` 实现（OpenAI tools 协议 + DeepSeek 兼容）
- `routes_agent.run` 接口能跑通：用规则 fallback 串起三个工具，输出和现有 `/api/pool/generate + /api/route/chain` 等价的结果
- `test_agent_minimal_flow.py`：不开 LLM key 时走 fallback，开 key 时调 LLM tool calling
- 前端 `DiscoveryFeedPage.submit` 走通 agent 路由（保留旧路由作 fallback）

Demo 点：API 调用回路通，结果和旧链路等价，证明骨架 OK。

### 阶段 2：UGC 真数据 + 向量化（3 天）

交付物：

- `scripts/synthesize_ugc.py` 跑完，产出 `data/processed/ugc_hefei.jsonl`（约 6000 条）
- `scripts/refine_hefei_categories.py` 跑完，POI category 分布合理
- `app/repositories/ugc_vector_repo.py` 实现 + ingest 脚本
- `app/agent/tools.py` 新增 `search_ugc_evidence` 工具
- `PoiScoringService._ugc_match_score` 接入真向量
- `PoolAgent` 第二阶段重排把 UGC evidence 附在候选 POI 上
- 前端 UGC feed 卡片显示真合成的 UGC，多样性可见

Demo 点：候选池有 cafe/restaurant/nightlife 分类，每张 UGC 卡片文案不一样，"为什么推荐"里能引一条 UGC 原文。

### 阶段 3：StoryAgent + Critic（3 天）

交付物：

- `app/agent/specialists/story_agent.py` + prompt 文件
- `app/agent/specialists/critic.py` + prompt 文件
- 工具 `compose_story / validate_route / critique` 注册
- Conductor 主循环升级到带 LLM tool calling + critic 回路（最多 critic 一次、重做一次）
- `_post_check` 幻觉检测（POI/UGC 都不能编）
- `StoryPlan` 进入 AgentMemory，最终 response 含 `theme / narrative / stops[].why / stops[].ugc_quote_ref`
- 前端 `AmapRoutePage` 标题用 theme、副标显示 narrative、每站可展开看引用 UGC 原文
- `test_story_agent.py`、`test_critic.py`、`test_agent_full_pipeline.py`

Demo 点：路线有故事化标题（"庐州本帮味 · 城东漫游"），每站 why 引一条 UGC 原文，evidence chain 完整。

### 阶段 4：反馈循环 + Agent 思考可视化（2 天）

交付物：

- `app/agent/specialists/repair_agent.py`：LLM 槽位抽取替代 `_detect_intent`
- 工具 `replan_by_event / parse_feedback` 注册
- `/api/agent/adjust` 接口，复用 Conductor，`goal.kind=adjust_route`
- 复合反馈（"换近的火锅+预算到 250"）能正确处理
- `app/agent/tracing.py` + SSE `/api/agent/stream/{session_id}`
- 前端 `AgentThinkingPanel` 组件 + CSS 抽屉
- `routes_meta` 加 `/api/agent/tools` 列出所有工具 + schema（方便评委看）

Demo 点：用户输入"第二站换近的火锅，预算 250"被正确拆成两个 delta；侧边栏滚动展示 agent 每一步思考；Agent 中途出错会显示 retry 和 fallback。

### 阶段 5（时间富余则做）：高级优化（2-3 天）

- 路线 ordering 用 orienteering / 2-opt 替代最近邻贪心
- Amap segment 缓存（按 origin+destination+mode key）
- transit / bicycling 模式支持
- Critic 引入 `should_replan` 触发 StoryAgent 重试
- 前端"Agent 评分卡片"展示 critique 5 维分数
- Conductor 支持并行调用工具（pool + ugc 同时）
- 多用户会话隔离与持久化

---

## 十、提示词工程清单

把所有 prompt 集中放 `app/agent/prompts/`，便于版本化和评测。建议每个 prompt 文件配套 `prompts/*.eval.jsonl`，存 10-20 条人工标注的 `(input, expected_output)`，搭配 `tests/test_prompt_regression.py` 做回归。Prompt 微调时 CI 跑这个测试，避免改一句话拖崩整个 agent。

每个 prompt 头部强制四件事：

1. 任务一句话说清；
2. 输入 schema 明确；
3. 输出严格 JSON schema 明确；
4. 幻觉禁令（"只能引用上文提供的 POI/UGC，不能编造"）。

---

## 十一、降级与可靠性设计

LLM 不可用时整套必须能跑。每个专家都有 `_rule_fallback`：

- **NeedAgent fallback**：现有 `IntentService._enhance_intent_with_llm` 那套规则（关键词扫描 + 默认值）
- **PoolAgent fallback**：现有 `PoolService.generate_pool` 一对一兼容
- **StoryAgent fallback**：用 `_nearest_order` 出顺序，理由用现有 `_strongest_score_factor` 一句话模板
- **Critic fallback**：纯规则审稿——"有 error 就 should_stop=False，否则 True"
- **Conductor fallback**：按 phase 走预设工具序列

Agent 整体熔断：单 session 步数 > 8、token > 6000、墙钟 > 30 秒、连续 3 步同工具，立刻切到旧 `/api/pool + /api/route/chain` 链路并返回，前端展示"Agent 退到稳定模式"提示。

---

## 十二、可观测性

每次 Conductor 调用产出一个 trace 文件 `data/traces/{trace_id}.json`，包含：

- goal、initial state
- 每个 ToolCall（args / observation_summary / latency / tokens）
- 最终 state、最终输出

前端 `/api/agent/trace/{session_id}` 接口给评委演示用。

加一个 `scripts/replay_trace.py`：

```python
def replay(trace_id: str):
    """加载历史 trace，重放每一步，对比观察是否一致。用于回归测试 prompt 变更。"""
```

---

## 十三、测试矩阵

`tests/agent/` 子目录，按层级覆盖：

- `test_tool_registry.py`：每个 tool 的 schema 合法、handler 不开 LLM 也能返回降级结果
- `test_specialists/test_need_agent.py` 等四个：用 mock LLM 测试每个专家的 prompt 拼接和 post-check
- `test_conductor.py`：mock 工具序列，断言 Conductor 在不同 goal 下选对工具、能正确终止
- `test_agent_e2e.py`：真实跑 fallback 模式下的端到端（无 LLM key），验证最终 response 合理
- `test_prompt_regression.py`：跑 prompt eval set，断言 JSON schema 校验通过率 > 95%
- `test_hallucination_check.py`：故意给 StoryAgent 注入幻觉 LLM 回复，断言 post-check 能识别并降级
- `test_demo_flow.py` 不动，作为旧链路回归

---

## 十四、Demo 脚本设计

赛前彩排按下面这条线讲故事：

**第一帧（30 秒）**：`DiscoveryFeedPage` 刷 UGC 流，用户随手 like 4-5 张卡（譬如老火锅、咖啡馆、夜市），点"现在出发"。

**第二帧（30-45 秒）**：右侧 "Agent 思考" 抽屉滑出，逐条显示：

- "在理解需求……" → 抽出"少排队、想拍照、夜场"
- "在召回 UGC 证据……" → 召回 17 条相关 UGC
- "在筛选候选池……" → 24 个 POI，分 4 类
- "在编排路线……" → 主题：庐州夏夜局
- "在校验可行性……" → 通过
- "在做最后审稿……" → 5 维评分 8.6 / 10
- "完成"

**第三帧（30 秒）**：高德地图渲染真实路线，标题"庐州夏夜局：火锅→咖啡→城东夜市"，每个 POI 点开看 why 引用的 UGC 原文（带"小红书 / 大众点评"角标）。

**第四帧（30 秒）**：用户输入"第二站换近的咖啡，预算到 250"。Agent 思考抽屉再次滚动，命中 `parse_feedback → replan_by_event` 两个工具，10 秒后路线更新。地图重绘新的 segment。

**第五帧（15 秒）**：评委可见 `/api/agent/trace/{session_id}` 的 trace 文件，证明全程可追溯、可重放。

整条 demo ≤ 3 分钟，能讲清楚 agent、UGC、reasoning、可解释性、稳定性五件事。

---

## 十五、风险与回避

- **LLM 输出不稳定**：所有专家都有 `_post_check` + retry + fallback 三件套，每个 LLM 调用都 JSON schema 校验。
- **Prompt 改一次塌一片**：用 `prompts/*.eval.jsonl` 回归保护，每次改 prompt 都跑回归测试。
- **Amap 配额**：segment 缓存（同 origin+destination+mode 复用），feedback 重算时只更新变化段。
- **UGC 合规**：用 LLM 仿写，不抓真实平台；最终 demo 时如果评委追问数据来源，老实说"合肥真实 POI + LLM 仿写 UGC"，避免触红线。
- **合肥单一 category**：阶段 2 的 `refine_hefei_categories` 脚本必须先跑。
- **赛前回归**：阶段 4 结束后留 1 天专门跑回归 + 修 bug + 录 demo 视频备份（防现场网络挂）。

---

## 十六、最终交付物盘点

**代码侧**：

- `app/agent/` 全套（conductor、4 个专家、tool registry、state、tracing、cache、policies、prompts）
- `app/repositories/ugc_vector_repo.py` + ingest 脚本
- `scripts/synthesize_ugc.py`、`scripts/refine_hefei_categories.py`、`scripts/replay_trace.py`
- 新 API `routes_agent.py`
- 新前端 `AgentThinkingPanel`、`AmapRoutePage` 主题/UGC evidence 展开

**数据侧**：

- `data/processed/hefei_pois.sqlite`（已有，补 `derived_category`）
- `data/processed/ugc_hefei.jsonl`（新增，约 6000 条）
- `data/processed/chroma/`（新增向量索引）
- `data/traces/*.json`（运行时产出）

**文档侧**：

- `docs/agent_architecture.md` 系统图
- `docs/prompts.md` 每个 prompt 的设计动机
- `docs/demo_script.md` 赛前彩排流程
- 更新 `README.md` 主链路从 `pool+route_chain` 改为 `agent`

**测试侧**：

- `tests/agent/*`（约 8 个文件）
- `tests/test_prompt_regression.py`
- 旧 `test_demo_flow.py` 保留作 legacy 回归

---

## 收尾

这套方案的核心立意是：**Agent 不是把现有代码套个 LLM 的皮，而是让 LLM 真的在做决策（选工具、串故事、审稿、应对反馈），让规则代码退到工具内部做兜底**。

在这个架构下，赛题要求的"根据 UGC 串联多个 POI 的 agent"三件事——UGC（真向量化数据 + 引用进 evidence）、串联（StoryAgent 编排叙事 + 角色 + UGC quote）、agent（Conductor tool calling + 多专家协作 + critic 反思 + 可追溯 trace）——每件都有清晰的代码落点，每件都能在 demo 里被肉眼看到。

建议从阶段 1 的 `app/agent/state.py` 和 `tools.py` 起手——这两个文件不依赖 LLM，可以先把 agent 形态的骨架立起来，让团队后续的所有改动都有明确的接入点。

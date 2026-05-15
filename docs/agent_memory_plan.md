# Agent 三层记忆完整开发计划

> 在现有 AIroute 多 Agent 架构（Conductor + 5 Specialist + FAISS RAG + SQLite Trace 持久化）基础上，加入工业界 agent memory 标准的三层结构：**情景记忆（Episodic）+ 语义记忆（Semantic / UserFacts）+ 向量化情景记忆（Vector Session Recall）**。
>
> 总工时约 3-4 天。按"先骨架后接通、先离线后实时、先正确后优化"分六个阶段，每阶段都能独立 commit 并跑通测试。

---

## 一、整体架构与数据流

三层记忆按"读 → 写 → 用"三个方向接进现有 agent loop：

```
Run start                Build state                 Conductor loop
   │                         │                             │
   ▼                         ▼                             ▼
load_state                 enrich(state)               tools.execute
  │                         ├─ episodic_summary  ◄─ list_sessions(user, 5)
  │                         ├─ user_facts        ◄─ derive_facts(user)
  │                         └─ similar_sessions  ◄─ session_vec.search(query)
  │                         ▼                             ▼
  │                       AgentState                  observation/memory_patch
  │                         │                             │
  │                         ▼                             ▼
  │                       Conductor.run() ─────────► tool: recall_similar_sessions
  │                                                       │
  │                                                       ▼
Run end                                              memory_patch:
  ├─ save_state(SQLite) ◄────────────────────────────  similar_sessions[]
  ├─ session_vec.add(state) ◄──────────────────────────  add this session
  └─ invalidate_facts_cache(user_id)
```

三层在不同生命周期点工作：

- **Working memory**：每个 tool 执行后通过 `memory_patch` 写 AgentMemory（已有）
- **Episodic memory**：build_initial_state 时读、save_state 时写
- **Semantic memory（UserFacts）**：build_initial_state 时按需 derive、有反馈时失效缓存
- **Vector session memory**：build_initial_state 时检索相似 session、save_state 后异步索引新 session

---

## 二、文件结构与新增模块

```
backend/app/
  agent/
    state.py                       [改] 加 episodic_summary / user_facts / similar_sessions
    conductor.py                   [改] _build_decision_prompt 加 memory 摘要
    tools.py                       [改] 新增 recall_similar_sessions 工具
    tool_schemas.py                [改] 新增 RECALL_SIMILAR_SESSIONS schema
    store.py                       [改] save_state 后触发 session_vec.add
    user_memory.py                 [新] UserFacts 模型 + derive_facts + 缓存
    session_summarizer.py          [新] AgentState → episodic summary dict
    specialists/
      story_agent.py               [改] prompt 加 past sessions + similar sessions block
  repositories/
    session_vector_repo.py         [新] FAISS 索引每个 user 的 session embeddings
  services/
    poi_scoring_service.py         [改] 加 fact_alignment 评分维度
  schemas/
    plan.py                        [改] ScoreBreakdown 加 fact_alignment
    user_memory.py                 [新] UserFacts / SessionSummary / SimilarSessionHit
  api/
    routes_agent.py                [改] 新增 /user/{user_id}/facts 端点

data/processed/
  agent_sessions.sqlite            [已有] 加 user_facts 表
  sessions/                        [新] 每个 user 一个 FAISS 文件
    {user_id}.faiss
    {user_id}.meta.jsonl

scripts/
  rebuild_session_index.py         [新] 批量重建所有 user 的 session 向量索引

tests/
  test_episodic_memory.py          [新] 验证跨 session 拉取摘要
  test_user_facts.py               [新] 验证 facts 派生与缓存
  test_session_vector.py           [新] 验证向量召回相似 session
  test_agent_memory_e2e.py         [新] 三层记忆联动 E2E

frontend/src/components/
  UserMemoryPanel.tsx              [新] 用户偏好画像展示
```

---

## 三、阶段 A：Schema 与基础模型（半天）

### A.1 新增 schema 文件

```python
# app/schemas/user_memory.py
from datetime import datetime
from pydantic import BaseModel, Field


class SessionSummary(BaseModel):
    """单次 session 浓缩成的可放进 prompt 的摘要"""
    session_id: str
    raw_query: str
    theme: str | None = None
    narrative: str | None = None
    stop_poi_ids: list[str] = Field(default_factory=list)
    stop_poi_names: list[str] = Field(default_factory=list)
    category_distribution: dict[str, int] = Field(default_factory=dict)
    feedback_applied: bool = False
    rejected_poi_ids: list[str] = Field(default_factory=list)
    created_at: datetime


class UserFacts(BaseModel):
    """从历史 session 派生的稳定用户事实"""
    user_id: str
    typical_budget_range: tuple[int, int] | None = None
    typical_party_type: str | None = None
    typical_time_windows: list[str] = Field(default_factory=list)
    favorite_districts: list[str] = Field(default_factory=list)
    favorite_categories: list[str] = Field(default_factory=list)
    avoid_categories: list[str] = Field(default_factory=list)
    rejected_poi_ids: list[str] = Field(default_factory=list)
    session_count: int = 0
    updated_at: datetime

    def to_prompt_block(self) -> str:
        """把 facts 序列化成 LLM prompt 里可读的一段话"""
        parts = []
        if self.typical_budget_range:
            lo, hi = self.typical_budget_range
            parts.append(f"typical_budget=¥{lo}-{hi}")
        if self.typical_party_type:
            parts.append(f"party={self.typical_party_type}")
        if self.favorite_categories:
            parts.append(f"likes={','.join(self.favorite_categories[:3])}")
        if self.avoid_categories:
            parts.append(f"avoids={','.join(self.avoid_categories)}")
        if self.rejected_poi_ids:
            parts.append(f"rejected={len(self.rejected_poi_ids)} POIs")
        return "; ".join(parts) if parts else "no facts yet"


class SimilarSessionHit(BaseModel):
    """向量召回的相似 session"""
    session_id: str
    raw_query: str
    theme: str | None
    similarity: float
    stop_poi_names: list[str] = Field(default_factory=list)
    days_ago: int = 0
```

### A.2 扩展 AgentMemory

```python
# app/agent/state.py
from app.schemas.user_memory import SessionSummary, SimilarSessionHit, UserFacts

class AgentMemory(BaseModel):
    # ... 现有字段保持

    # 新增三层记忆
    episodic_summary: list[SessionSummary] = Field(default_factory=list)
    user_facts: UserFacts | None = None
    similar_sessions: list[SimilarSessionHit] = Field(default_factory=list)
    similar_sessions_searched: bool = False
```

### A.3 ScoreBreakdown 加一维

```python
# app/schemas/plan.py
class ScoreBreakdown(BaseModel):
    # ... 已有 10 个维度
    fact_alignment: float = 0.0   # 与 user_facts 的对齐度，-10 到 +10
    total: float = 0.0
```

### A.4 SQLite schema 升级

```python
# app/agent/store.py 的 _SCHEMA 末尾追加
_SCHEMA = """
... 已有 agent_sessions 表 ...

CREATE TABLE IF NOT EXISTS user_facts (
    user_id TEXT PRIMARY KEY,
    facts_json TEXT NOT NULL,
    session_count INTEGER NOT NULL DEFAULT 0,
    last_session_id TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_facts_updated ON user_facts(updated_at DESC);
"""
```

---

## 四、阶段 B：情景记忆（Day 1 全天）

### B.1 实现 session_summarizer

```python
# app/agent/session_summarizer.py
from collections import Counter
from datetime import datetime

from app.agent.state import AgentState
from app.repositories.poi_repo import get_poi_repository
from app.schemas.user_memory import SessionSummary


def summarize_session(state: AgentState) -> SessionSummary:
    repo = get_poi_repository()
    story = state.memory.story_plan
    rejected = _extract_rejected_pois(state)

    stop_ids = [stop.poi_id for stop in story.stops] if story else []
    stop_names = []
    categories = Counter()
    for poi_id in stop_ids:
        try:
            poi = repo.get(poi_id)
            stop_names.append(poi.name)
            categories[poi.category] += 1
        except KeyError:
            stop_names.append(poi_id)

    return SessionSummary(
        session_id=state.goal.session_id,
        raw_query=state.goal.raw_query,
        theme=story.theme if story else None,
        narrative=story.narrative if story else None,
        stop_poi_ids=stop_ids,
        stop_poi_names=stop_names,
        category_distribution=dict(categories),
        feedback_applied=state.memory.feedback_applied,
        rejected_poi_ids=rejected,
        created_at=datetime.utcnow(),
    )


def _extract_rejected_pois(state: AgentState) -> list[str]:
    """从 feedback_intent 抽取被替换/拒绝的 POI"""
    feedback = state.memory.feedback_intent
    if not feedback:
        return []
    if feedback.get("event_type") != "REPLACE_POI":
        return []
    target_index = feedback.get("target_stop_index")
    if target_index is None:
        return []
    original = feedback.get("_original_poi_at_target")
    return [original] if original else []
```

`_extract_rejected_pois` 依赖 RepairAgent 在替换之前把原 POI 存进 feedback_intent。要在 `tools._replan_by_event` 里加一行：

```python
# app/agent/tools.py 改 _replan_by_event
def _replan_by_event(state, args):
    feedback = state.memory.feedback_intent or {}
    story = state.memory.story_plan
    ...
    target_index = ...
    if updated.stops and 0 <= target_index < len(updated.stops):
        # 新增：记录被替换的原 POI
        feedback["_original_poi_at_target"] = updated.stops[target_index].poi_id
        state.memory.feedback_intent = feedback
        # ... 现有替换逻辑
```

### B.2 build_initial_state 注入 episodic_summary

```python
# app/api/routes_agent.py
from app.agent.session_summarizer import summarize_session
from app.agent.store import list_sessions

def build_initial_state(request: AgentRunRequest) -> AgentState:
    session_id = request.session_id or uuid4().hex
    context = PlanContext(...)
    profile = UserNeedProfile.from_plan_context(context, raw_query=request.free_text)
    profile.user_id = request.user_id

    state = AgentState(
        goal=AgentGoal(...),
        profile=profile,
        preference=request.preference_snapshot,
        context=context,
    )

    # 新增：拉最近 5 个 session 摘要
    past_sessions = list_sessions(request.user_id, limit=5)
    state.memory.episodic_summary = [summarize_session(s) for s in past_sessions]

    return state
```

### B.3 StoryAgent prompt 接入

```python
# app/agent/specialists/story_agent.py
def _build_prompt(self, candidates, state):
    rows = [...]  # 已有

    # 新增：past sessions block
    past_block = ""
    if state.memory.episodic_summary:
        past_lines = []
        for past in state.memory.episodic_summary[:3]:
            past_lines.append(
                f"- {past.created_at:%Y-%m-%d}: query={past.raw_query!r} "
                f"→ theme={past.theme!r} | stops={','.join(past.stop_poi_names[:3])}"
            )
        past_block = "\n\nUser's recent route history (avoid repeating themes):\n" + "\n".join(past_lines)

    return (
        f"Build a 3-5 stop route story.\n"
        f"Return JSON with theme, narrative, stops, dropped, fallback_used.\n"
        f"query={state.goal.raw_query}\n"
        f"candidates={rows}"
        f"{past_block}"
    )
```

### B.4 测试

```python
# tests/test_episodic_memory.py
from app.agent.session_summarizer import summarize_session
from app.agent.store import save_state, list_sessions
from app.api.routes_agent import build_initial_state, AgentRunRequest


def test_session_summary_captures_theme_and_stops(_state_with_story_plan):
    summary = summarize_session(_state_with_story_plan)
    assert summary.theme == "Local Taste Route"
    assert len(summary.stop_poi_ids) >= 3
    assert summary.category_distribution.get("restaurant", 0) >= 1


def test_build_initial_state_loads_past_summaries(tmp_path, monkeypatch):
    monkeypatch.setattr("app.agent.store.DB_PATH", tmp_path / "test.sqlite", raising=False)

    for i in range(2):
        state = _make_completed_state(user_id="alice", session_id=f"s_{i}")
        save_state(state)

    request = AgentRunRequest(
        user_id="alice",
        free_text="想吃火锅",
        city="hefei",
        date="2026-05-08",
        time_window={"start": "12:00", "end": "20:00"},
    )
    new_state = build_initial_state(request)

    assert len(new_state.memory.episodic_summary) == 2
    assert all(s.raw_query for s in new_state.memory.episodic_summary)


def test_story_agent_prompt_includes_past_history(_state_with_two_sessions_history):
    prompt = StoryAgent()._build_prompt([], _state_with_two_sessions_history)
    assert "recent route history" in prompt
    assert "avoid repeating themes" in prompt
```

**阶段 B 验收**：跑 `pytest tests/test_episodic_memory.py -v` 全绿；用 `curl /api/agent/run` 跑两次相同 user_id，第二次的 `steps` 里 compose_story 的 prompt（开 LLM 时）能看到第一次的摘要。

---

## 五、阶段 C：语义记忆 UserFacts（Day 2 上午）

### C.1 实现 user_memory.py

```python
# app/agent/user_memory.py
from collections import Counter
from datetime import datetime, timedelta, timezone

from app.agent.store import list_sessions, _conn
from app.agent.session_summarizer import summarize_session
from app.schemas.user_memory import UserFacts


# 内存 cache，避免每次 build_state 都 derive
_CACHE: dict[str, tuple[UserFacts, datetime]] = {}
CACHE_TTL = timedelta(minutes=5)


def get_user_facts(user_id: str, *, force_refresh: bool = False) -> UserFacts:
    """优先读 SQLite cache，过期或强制刷新则 derive"""
    now = datetime.now(timezone.utc)

    if not force_refresh:
        cached = _CACHE.get(user_id)
        if cached and now - cached[1] < CACHE_TTL:
            return cached[0]

        row = _read_facts_row(user_id)
        if row and now - _parse_dt(row["updated_at"]) < CACHE_TTL:
            facts = UserFacts.model_validate_json(row["facts_json"])
            _CACHE[user_id] = (facts, now)
            return facts

    facts = derive_facts(user_id)
    _write_facts_row(facts)
    _CACHE[user_id] = (facts, now)
    return facts


def invalidate_facts(user_id: str) -> None:
    _CACHE.pop(user_id, None)


def derive_facts(user_id: str) -> UserFacts:
    sessions = list_sessions(user_id, limit=50)
    if not sessions:
        return UserFacts(user_id=user_id, updated_at=datetime.now(timezone.utc))

    summaries = [summarize_session(s) for s in sessions]

    # 预算范围
    budgets = [
        s.context.budget_per_person for s in sessions
        if s.context.budget_per_person
    ]
    budget_range = (min(budgets), max(budgets)) if budgets else None

    # 高频 party_type
    party_types = [s.context.party for s in sessions if s.context.party]
    typical_party = max(set(party_types), key=party_types.count) if party_types else None

    # 高频时间窗
    time_buckets = [_bucket_time_window(s) for s in sessions]
    typical_times = [t for t, _ in Counter(time_buckets).most_common(2) if t]

    # 类目偏好：累积所有 session 的 category_distribution
    category_total = Counter()
    for summary in summaries:
        category_total.update(summary.category_distribution)
    favorite_cats = [c for c, _ in category_total.most_common(3)]

    # 拒绝过的 POI
    rejected_pois = []
    for summary in summaries:
        rejected_pois.extend(summary.rejected_poi_ids)
    rejected_pois = list(dict.fromkeys(rejected_pois))[-20:]   # 截断到最近 20 个

    # 推断 avoid_categories
    rejected_categories = _infer_avoid_categories(sessions, rejected_pois)

    # 商圈偏好
    favorite_districts = _favorite_districts(summaries)

    return UserFacts(
        user_id=user_id,
        typical_budget_range=budget_range,
        typical_party_type=typical_party,
        typical_time_windows=typical_times,
        favorite_districts=favorite_districts,
        favorite_categories=favorite_cats,
        avoid_categories=rejected_categories,
        rejected_poi_ids=rejected_pois,
        session_count=len(sessions),
        updated_at=datetime.now(timezone.utc),
    )


def _bucket_time_window(state) -> str | None:
    try:
        date_obj = datetime.fromisoformat(state.context.date)
        is_weekend = date_obj.weekday() >= 5
        start_hour = int(state.context.time_window.start.split(":")[0])
        if start_hour < 12:
            period = "morning"
        elif start_hour < 17:
            period = "afternoon"
        else:
            period = "evening"
        prefix = "weekend" if is_weekend else "weekday"
        return f"{prefix}_{period}"
    except (ValueError, AttributeError):
        return None


def _infer_avoid_categories(sessions, rejected_pois: list[str]) -> list[str]:
    if not rejected_pois:
        return []
    from app.repositories.poi_repo import get_poi_repository
    repo = get_poi_repository()
    rejected_cats = []
    for poi_id in rejected_pois:
        try:
            rejected_cats.append(repo.get(poi_id).category)
        except KeyError:
            continue
    counter = Counter(rejected_cats)
    return [cat for cat, count in counter.items() if count >= 2]


def _favorite_districts(summaries) -> list[str]:
    from app.repositories.poi_repo import get_poi_repository
    repo = get_poi_repository()
    districts = Counter()
    for summary in summaries:
        for poi_id in summary.stop_poi_ids:
            try:
                poi = repo.get(poi_id)
                district = poi.address.split(",")[0].split(" ")[-1] if poi.address else None
                if district:
                    districts[district] += 1
            except KeyError:
                continue
    return [d for d, _ in districts.most_common(3)]


def _read_facts_row(user_id: str):
    with _conn() as conn:
        return conn.execute(
            "SELECT facts_json, updated_at FROM user_facts WHERE user_id = ?",
            (user_id,),
        ).fetchone()


def _write_facts_row(facts: UserFacts) -> None:
    with _conn() as conn:
        conn.execute(
            """INSERT INTO user_facts (user_id, facts_json, session_count, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 facts_json = excluded.facts_json,
                 session_count = excluded.session_count,
                 updated_at = excluded.updated_at""",
            (facts.user_id, facts.model_dump_json(), facts.session_count,
             facts.updated_at.isoformat()),
        )


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
```

### C.2 接入 build_initial_state 与 IntentService

```python
# app/api/routes_agent.py
from app.agent.user_memory import get_user_facts

def build_initial_state(request: AgentRunRequest) -> AgentState:
    # ... 已有
    state.memory.episodic_summary = [summarize_session(s) for s in past_sessions]
    state.memory.user_facts = get_user_facts(request.user_id)

    # 把 rejected_poi_ids 注入 profile，让后续 intent 自动 avoid
    if state.memory.user_facts and state.memory.user_facts.rejected_poi_ids:
        state.profile.must_avoid = list(set(
            state.profile.must_avoid + state.memory.user_facts.rejected_poi_ids
        ))

    return state
```

### C.3 parse_intent 工具消费 facts

```python
# app/agent/tools.py 改 _rule_parse_intent
def _rule_parse_intent(state, free_text, selected_poi_ids):
    # ... 已有逻辑

    # 新增：把 user_facts.rejected_poi_ids 进 avoid_pois
    avoid_pois = []
    if state.memory.user_facts:
        avoid_pois.extend(state.memory.user_facts.rejected_poi_ids)

    # 新增：budget 没填时用 typical_budget_range 中位
    if budget_total is None and state.memory.user_facts and state.memory.user_facts.typical_budget_range:
        lo, hi = state.memory.user_facts.typical_budget_range
        budget_total = (lo + hi) // 2

    return StructuredIntent(
        hard_constraints=HardConstraints(..., budget_total=budget_total),
        soft_preferences=SoftPreferences(...),
        must_visit_pois=selected_poi_ids,
        avoid_pois=avoid_pois,
    )
```

### C.4 PoiScoringService 加 fact_alignment

```python
# app/services/poi_scoring_service.py
def score_poi(self, poi, *, intent=None, context=None, profile=None,
              preference_snapshot=None, free_text=None, user_facts=None):
    # ... 已有维度
    fact_alignment = self._fact_alignment_score(poi, user_facts)

    total = (
        user_interest + poi_quality + context_fit + ugc_match
        + service_closure + history_preference + queue_penalty
        + price_penalty + distance_penalty + risk_penalty
        + fact_alignment   # 新增
    )
    return ScoreBreakdown(..., fact_alignment=round(fact_alignment, 2), total=round(total, 2))


def _fact_alignment_score(self, poi, facts) -> float:
    if facts is None:
        return 0.0
    score = 0.0
    if poi.id in facts.rejected_poi_ids:
        score -= 10.0
    if poi.category in facts.favorite_categories:
        score += 4.0
    if poi.category in facts.avoid_categories:
        score -= 6.0
    if facts.typical_budget_range and poi.price_per_person:
        lo, hi = facts.typical_budget_range
        if lo <= poi.price_per_person <= hi:
            score += 2.0
    return max(-10.0, min(score, 10.0))
```

调用方在 `tools._recommend_pool` 把 `state.memory.user_facts` 传进 `PoolService.generate_pool`（PoolService 内部转给 PoiScoringService.score_poi）。

### C.5 save_state 触发 facts 失效

```python
# app/agent/store.py
from app.agent.user_memory import invalidate_facts

def save_state(state: AgentState) -> None:
    # ... 已有插入逻辑
    invalidate_facts(state.goal.user_id)
```

### C.6 API 端点

```python
# app/api/routes_agent.py
from app.agent.user_memory import get_user_facts

@router.get("/user/{user_id}/facts")
def get_user_facts_endpoint(user_id: str, force_refresh: bool = False) -> UserFacts:
    return get_user_facts(user_id, force_refresh=force_refresh)
```

### C.7 测试

```python
# tests/test_user_facts.py
def test_derive_facts_from_zero_sessions_returns_empty():
    facts = derive_facts("new_user_xyz")
    assert facts.session_count == 0
    assert facts.typical_budget_range is None


def test_derive_facts_picks_majority_party_type(_three_sessions_friends_1_couple):
    facts = derive_facts("u1")
    assert facts.typical_party_type == "friends"


def test_derive_facts_avoid_categories_after_two_rejections(_user_with_two_cafe_rejections):
    facts = derive_facts("u1")
    assert "cafe" in facts.avoid_categories


def test_rejected_pois_auto_enter_avoid_pois(monkeypatch, tmp_path):
    # save 一个 session 含 REPLACE_POI feedback
    # 新 session run，验证 intent.avoid_pois 包含被替换的 POI
    ...


def test_facts_cache_invalidates_on_new_session_save(...):
    facts_v1 = get_user_facts("u1")
    save_state(_new_session(user="u1"))
    facts_v2 = get_user_facts("u1")
    assert facts_v2.session_count == facts_v1.session_count + 1


def test_fact_alignment_dimension_in_score_breakdown(_poi_in_rejected_list):
    score = PoiScoringService().score_poi(poi, user_facts=facts_with_rejection)
    assert score.fact_alignment <= -8.0
    assert score.total < 0
```

**阶段 C 验收**：facts 派生测试全绿，API `GET /api/agent/user/u1/facts` 返回正确结构，PoolService 输出的 candidates 在 rejected_poi_ids 里的 POI 排名明显靠后。

---

## 六、阶段 D：向量化情景记忆（Day 2 下午 + Day 3 上午）

### D.1 实现 SessionVectorRepo

```python
# app/repositories/session_vector_repo.py
import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.agent.state import AgentState
from app.schemas.user_memory import SessionSummary, SimilarSessionHit


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SESSIONS_DIR = PROJECT_ROOT / "data" / "processed" / "sessions"
MODEL_NAME = "BAAI/bge-small-zh-v1.5"


class SessionVectorRepo:
    def __init__(self, sessions_dir: Path | None = None) -> None:
        self._dir = sessions_dir or SESSIONS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._indexes: dict[str, Any] = {}
        self._metas: dict[str, list[dict]] = {}
        self._model = None

    def add_session(self, state: AgentState, summary: SessionSummary) -> None:
        """save_state 后调用，把 session 加入用户索引"""
        text = self._session_to_text(summary, state.goal.raw_query)
        if not text.strip():
            return
        emb = self._encode(text)
        if emb is None:
            return
        index, metas = self._get_or_create_index(state.goal.user_id, dim=emb.shape[0])
        index.add(emb.reshape(1, -1))
        metas.append({
            "session_id": summary.session_id,
            "raw_query": summary.raw_query,
            "theme": summary.theme,
            "stop_poi_names": summary.stop_poi_names,
            "created_at": summary.created_at.isoformat(),
        })
        self._persist(state.goal.user_id, index, metas)

    def search_similar(
        self, user_id: str, query: str, *,
        top_k: int = 3, exclude_session_id: str | None = None,
    ) -> list[SimilarSessionHit]:
        if not query.strip():
            return []
        emb = self._encode(query)
        if emb is None:
            return []
        loaded = self._load_user_index(user_id)
        if loaded is None:
            return []
        index, metas = loaded
        if index.ntotal == 0:
            return []

        search_k = min(top_k + 5, index.ntotal)
        scores, indices = index.search(emb.reshape(1, -1), search_k)

        hits = []
        now = datetime.now(timezone.utc)
        for score, idx in zip(scores[0], indices[0]):
            idx = int(idx)
            if idx < 0 or idx >= len(metas):
                continue
            meta = metas[idx]
            if exclude_session_id and meta["session_id"] == exclude_session_id:
                continue
            created = datetime.fromisoformat(meta["created_at"]).replace(tzinfo=timezone.utc)
            hits.append(SimilarSessionHit(
                session_id=meta["session_id"],
                raw_query=meta["raw_query"],
                theme=meta.get("theme"),
                similarity=float(score),
                stop_poi_names=meta.get("stop_poi_names", []),
                days_ago=(now - created).days,
            ))
            if len(hits) >= top_k:
                break
        return hits

    def _session_to_text(self, summary: SessionSummary, raw_query: str) -> str:
        parts = [raw_query]
        if summary.theme:
            parts.append(summary.theme)
        if summary.narrative:
            parts.append(summary.narrative)
        if summary.stop_poi_names:
            parts.append(" ".join(summary.stop_poi_names))
        return " | ".join(parts)

    def _encode(self, text: str):
        try:
            if self._model is None:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(MODEL_NAME)
            import numpy as np
            return np.asarray(
                self._model.encode(text, normalize_embeddings=True),
                dtype="float32",
            )
        except Exception:
            return None

    def _get_or_create_index(self, user_id: str, *, dim: int):
        if user_id in self._indexes:
            return self._indexes[user_id], self._metas[user_id]
        loaded = self._load_user_index(user_id)
        if loaded is not None:
            self._indexes[user_id], self._metas[user_id] = loaded
            return loaded
        import faiss
        index = faiss.IndexFlatIP(dim)
        self._indexes[user_id] = index
        self._metas[user_id] = []
        return index, self._metas[user_id]

    def _load_user_index(self, user_id: str):
        if user_id in self._indexes:
            return self._indexes[user_id], self._metas[user_id]
        index_path = self._dir / f"{user_id}.faiss"
        meta_path = self._dir / f"{user_id}.meta.jsonl"
        if not (index_path.exists() and meta_path.exists()):
            return None
        try:
            import faiss
            index = faiss.read_index(str(index_path))
            metas = [json.loads(line) for line in meta_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self._indexes[user_id] = index
            self._metas[user_id] = metas
            return index, metas
        except Exception:
            return None

    def _persist(self, user_id: str, index, metas: list[dict]) -> None:
        try:
            import faiss
            index_path = self._dir / f"{user_id}.faiss"
            meta_path = self._dir / f"{user_id}.meta.jsonl"
            faiss.write_index(index, str(index_path))
            meta_path.write_text(
                "\n".join(json.dumps(m, ensure_ascii=False) for m in metas),
                encoding="utf-8",
            )
        except Exception:
            pass


@lru_cache
def get_session_vector_repo() -> SessionVectorRepo:
    return SessionVectorRepo()
```

### D.2 save_state 触发索引

```python
# app/agent/store.py
from app.repositories.session_vector_repo import get_session_vector_repo
from app.agent.session_summarizer import summarize_session

def save_state(state: AgentState) -> None:
    # ... 已有 SQLite 插入
    invalidate_facts(state.goal.user_id)

    # 新增：把 session 加入向量索引
    try:
        summary = summarize_session(state)
        get_session_vector_repo().add_session(state, summary)
    except Exception:
        pass  # 索引失败不影响主流程
```

### D.3 build_initial_state 注入 similar_sessions

```python
# app/api/routes_agent.py
from app.repositories.session_vector_repo import get_session_vector_repo

def build_initial_state(request: AgentRunRequest) -> AgentState:
    # ... 已有
    state.memory.episodic_summary = [...]
    state.memory.user_facts = get_user_facts(request.user_id)

    # 新增：向量召回相似 session
    state.memory.similar_sessions = get_session_vector_repo().search_similar(
        request.user_id,
        request.free_text,
        top_k=3,
        exclude_session_id=session_id,
    )
    state.memory.similar_sessions_searched = True

    return state
```

### D.4 新增工具 recall_similar_sessions

```python
# app/agent/tool_schemas.py
RECALL_SIMILAR_SESSIONS = {
    "name": "recall_similar_sessions",
    "description": "Retrieve semantically similar past sessions from the user's history for reference.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer"},
        },
        "required": ["query"],
    },
}
# 加进 TOOL_SCHEMAS 列表
```

```python
# app/agent/tools.py
def _recall_similar_sessions(state, args):
    query = str(args.get("query") or state.goal.raw_query)
    top_k = int(args.get("top_k") or 3)
    hits = get_session_vector_repo().search_similar(
        state.goal.user_id, query, top_k=top_k,
        exclude_session_id=state.goal.session_id,
    )
    return ToolResult(
        observation_summary=f"Recalled {len(hits)} similar past sessions.",
        payload=hits,
        memory_patch={"similar_sessions": hits, "similar_sessions_searched": True},
    )

# 注册到 get_tool_registry
Tool("recall_similar_sessions", tool_schemas.RECALL_SIMILAR_SESSIONS, _recall_similar_sessions),
```

### D.5 StoryAgent prompt 加 similar sessions

```python
# app/agent/specialists/story_agent.py
def _build_prompt(self, candidates, state):
    # ... 已有的 past_block

    similar_block = ""
    if state.memory.similar_sessions:
        sim_lines = []
        for hit in state.memory.similar_sessions[:2]:
            sim_lines.append(
                f"- {hit.days_ago}d ago: query={hit.raw_query!r} "
                f"→ theme={hit.theme!r} | stops={','.join(hit.stop_poi_names[:3])} "
                f"(similarity={hit.similarity:.2f})"
            )
        similar_block = (
            "\n\nSemantically similar past sessions (consider variation):\n"
            + "\n".join(sim_lines)
        )

    return f"...{past_block}{similar_block}"
```

### D.6 重建脚本

```python
# scripts/rebuild_session_index.py
"""遍历 agent_sessions.sqlite，给所有用户重建 FAISS 索引。"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.agent.store import _conn
from app.agent.session_summarizer import summarize_session
from app.agent.state import AgentState
from app.repositories.session_vector_repo import SessionVectorRepo


def main():
    repo = SessionVectorRepo()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT state_json FROM agent_sessions ORDER BY created_at ASC"
        ).fetchall()

    print(f"Rebuilding session index from {len(rows)} sessions...")
    for row in rows:
        state = AgentState.model_validate_json(row[0])
        summary = summarize_session(state)
        repo.add_session(state, summary)
    print("Done.")


if __name__ == "__main__":
    main()
```

### D.7 测试

```python
# tests/test_session_vector.py
def test_add_and_search_session_returns_self(tmp_path, monkeypatch):
    monkeypatch.setattr(...)  # mock SentenceTransformer + faiss with fake
    repo = SessionVectorRepo(sessions_dir=tmp_path)

    state = _completed_state(user="alice", query="火锅 安静 朋友")
    summary = summarize_session(state)
    repo.add_session(state, summary)

    hits = repo.search_similar("alice", "火锅", top_k=2)
    assert len(hits) >= 1
    assert hits[0].theme is not None


def test_search_excludes_current_session():
    repo = SessionVectorRepo(...)
    repo.add_session(_state("s1", "u1", "火锅"), summary1)

    hits = repo.search_similar("u1", "火锅", top_k=3, exclude_session_id="s1")
    assert all(hit.session_id != "s1" for hit in hits)


def test_search_returns_empty_for_new_user():
    repo = SessionVectorRepo(...)
    assert repo.search_similar("never_seen", "anything") == []


def test_conductor_recall_tool_appears_in_registry():
    names = {t["name"] for t in get_tool_registry().schemas_for_llm()}
    assert "recall_similar_sessions" in names
```

**阶段 D 验收**：跑 `python scripts/rebuild_session_index.py`，`data/processed/sessions/` 下出现每个 user 的 .faiss 和 .meta.jsonl；新建 session 后立刻能召回上一条；`test_session_vector.py` 全绿。

---

## 七、阶段 E：联动测试 + 前端展示（Day 3 下午）

### E.1 三层联动 E2E

```python
# tests/test_agent_memory_e2e.py
def test_three_layer_memory_end_to_end(monkeypatch, tmp_path):
    _patch_route_client(monkeypatch)
    monkeypatch.setattr("app.agent.store.DB_PATH", tmp_path / "test.sqlite")

    # 第 1 次 run：用户问"想吃火锅"
    r1 = client.post("/api/agent/run", json={
        "user_id": "alice",
        "free_text": "想吃火锅",
        ...
    }).json()

    # 第 2 次 run：反馈"换掉第一站"
    client.post("/api/agent/adjust", json={
        "parent_session_id": r1["session_id"],
        "user_message": "换掉第一站",
    })

    # 第 3 次 run：再问"想吃火锅"
    r3 = client.post("/api/agent/run", json={
        "user_id": "alice",
        "free_text": "想吃火锅",
        ...
    }).json()

    rejected_poi = r1["story_plan"]["stops"][0]["poi_id"]

    # 1. 情景记忆：r3 prompt 应含 r1 摘要
    # 2. 语义记忆：r3 的 story_plan 不应再包含 rejected_poi
    r3_stop_ids = [s["poi_id"] for s in r3["story_plan"]["stops"]]
    assert rejected_poi not in r3_stop_ids

    # 3. 向量记忆：通过 /api/agent/user/alice 验证 similar_sessions 已索引
    facts = client.get("/api/agent/user/alice/facts").json()
    assert facts["session_count"] >= 2
```

### E.2 前端展示

```tsx
// frontend/src/components/UserMemoryPanel.tsx
import { useEffect, useState } from "react"
import type { UserFacts } from "../types/userMemory"

export function UserMemoryPanel({ userId }: { userId: string }) {
  const [facts, setFacts] = useState<UserFacts | null>(null)

  useEffect(() => {
    fetch(`/api/agent/user/${userId}/facts`)
      .then(r => r.json())
      .then(setFacts)
  }, [userId])

  if (!facts || facts.session_count === 0) return null

  return (
    <aside className="user-memory-panel">
      <strong>Agent 已记住你的偏好</strong>
      <ul>
        {facts.typical_budget_range && (
          <li>典型预算 ¥{facts.typical_budget_range[0]}-{facts.typical_budget_range[1]}</li>
        )}
        {facts.typical_party_type && <li>常和 {facts.typical_party_type} 出行</li>}
        {facts.favorite_categories.length > 0 && (
          <li>偏好：{facts.favorite_categories.join("、")}</li>
        )}
        {facts.avoid_categories.length > 0 && (
          <li>避开：{facts.avoid_categories.join("、")}</li>
        )}
        {facts.rejected_poi_ids.length > 0 && (
          <li>历史拒绝 {facts.rejected_poi_ids.length} 个 POI</li>
        )}
      </ul>
      <small>{facts.session_count} 次会话累积</small>
    </aside>
  )
}
```

挂到 `DiscoveryFeedPage` 顶部 liked-strip 旁边。

### E.3 Conductor prompt 加 user_facts

```python
# app/agent/conductor.py
def _build_decision_prompt(self, state):
    completed = [step.tool_name for step in state.steps]
    facts_block = ""
    if state.memory.user_facts and state.memory.user_facts.session_count > 0:
        facts_block = f"; user_facts={state.memory.user_facts.to_prompt_block()}"
    return (
        "Choose the next AIroute agent tool. "
        f"phase={state.phase}; completed={completed}; "
        # ... 已有
        f"{facts_block}"
    )
```

---

## 八、阶段 F：收尾与验证（Day 4 上午）

### F.1 全套测试

```bash
pytest tests/test_episodic_memory.py -v
pytest tests/test_user_facts.py -v
pytest tests/test_session_vector.py -v
pytest tests/test_agent_memory_e2e.py -v
pytest tests/ -v   # 所有测试 ≥ 30 个，全部绿
```

### F.2 跑一次手动验证

```bash
# 启动后端
uvicorn app.main:app --port 8000

# 跑第一次 session
curl -X POST localhost:8000/api/agent/run -d '{
  "user_id": "demo_user",
  "free_text": "想吃合肥本地菜，少排队",
  "city": "hefei",
  "date": "2026-05-08",
  "time_window": {"start": "12:00", "end": "20:00"},
  "budget_per_person": 150
}' | jq '.story_plan.theme, .session_id'

# 跑反馈
curl -X POST localhost:8000/api/agent/adjust -d '{
  "parent_session_id": "<上一步的 session_id>",
  "user_message": "换掉第一站"
}'

# 第二次 session（同 user_id）
curl -X POST localhost:8000/api/agent/run -d '{
  "user_id": "demo_user",
  "free_text": "再来一次本地菜",
  ...
}' | jq '.story_plan.stops[].poi_id'

# 查 facts
curl localhost:8000/api/agent/user/demo_user/facts | jq
```

### F.3 文档与简历

更新 `docs/agent_development_plan.md` 加一节 Memory System，更新 README 架构图。简历 bullet 改成：

> Designed a **3-layer agent memory system**: per-session working memory (AgentState), persistent episodic memory in SQLite with cross-session summary injection into prompts, semantic user facts (rejected POIs, typical budget/party/category preferences) derived from history and auto-applied as soft constraints, and **vector-based session recall** using FAISS over BGE embeddings of past route narratives. Verified by E2E tests showing the agent skips previously-rejected POIs and proposes thematically diverse routes across sessions.

---

## 九、时间表与里程碑

| Day | 上午 | 下午 | 验收 |
|---|---|---|---|
| 1 | A 阶段 schema + AgentMemory 扩展 | B 阶段 episodic_summary + StoryAgent prompt 集成 | `test_episodic_memory.py` 全绿 |
| 2 | C 阶段 UserFacts derive + cache + 注入 | C 阶段 fact_alignment 评分 + API 端点 | `test_user_facts.py` 全绿、facts API 返回正确 |
| 3 | D 阶段 SessionVectorRepo + save_state 钩 | D 阶段 recall 工具 + prompt 集成 | `test_session_vector.py` 全绿、rebuild 脚本能跑 |
| 4 | E 阶段 E2E 测试 + 前端 UserMemoryPanel | F 阶段 手动验证 + 文档 + 简历更新 | 所有测试 ≥ 30 个全绿、demo 流程跑通 |

---

## 十、风险与回避

**风险 1：sentence-transformers 加载慢拖延启动**。SessionVectorRepo 懒加载 model，第一次 `add_session` 或 `search_similar` 才装载，首次 1-2 秒，后续常驻。生产部署可在 startup hook 里预热。

**风险 2：FAISS 跨用户索引文件膨胀**。每个 user 一个 .faiss 文件，1000 个用户 × 50 session × 512 维 = 100MB 量级，仍可控；万用户级别要换成单大索引 + user_id 元数据过滤。

**风险 3：UserFacts 缓存窗口太长导致反馈不实时**。`CACHE_TTL = 5 min` 是个折衷，save_state 时主动 invalidate，再 derive 时基本能拿到最新。如果 demo 时反馈后想立刻看 facts 变化，给 API 加 `?force_refresh=true` 参数。

**风险 4：rejected_poi_ids 越积越多 → avoid_pois 越来越大**。给 derive_facts 加截断：`rejected_pois = rejected_pois[-20:]`（只保留最近 20 个）。同时 facts schema 加 `rejected_threshold` 字段供前端展示"超过 20 个不再保留"。

**风险 5：embedding 跨 session 不一致**。如果中途换了模型，旧索引和新查询向量不匹配。`rebuild_session_index.py` 是兜底，部署文档里写"换模型后必须重建"。

**风险 6：测试环境无 BGE/FAISS 导致 D 阶段测试卡死**。`SessionVectorRepo._encode` catch `ImportError` 返回 None，让搜索返回空——测试可以用 fake faiss + fake model 注入。test_session_vector.py 都按这套写。

**风险 7：concurrent write race**。SQLite 单文件多写有锁，但 FAISS 文件不是线程安全的。Demo 单用户场景不会撞，生产要加 `threading.Lock` 包 `add_session` 或换 worker 内单实例 + `lru_cache`。

---

## 十一、最终文件清单

**新增 6 个**：

```
backend/app/agent/user_memory.py
backend/app/agent/session_summarizer.py
backend/app/repositories/session_vector_repo.py
backend/app/schemas/user_memory.py
scripts/rebuild_session_index.py
frontend/src/components/UserMemoryPanel.tsx
```

**修改 10 个**：

```
backend/app/agent/state.py
backend/app/agent/conductor.py
backend/app/agent/tools.py
backend/app/agent/tool_schemas.py
backend/app/agent/store.py
backend/app/agent/specialists/story_agent.py
backend/app/api/routes_agent.py
backend/app/services/poi_scoring_service.py
backend/app/schemas/plan.py
frontend/src/pages/DiscoveryFeedPage.tsx
```

**新增 4 个测试**：

```
backend/tests/test_episodic_memory.py
backend/tests/test_user_facts.py
backend/tests/test_session_vector.py
backend/tests/test_agent_memory_e2e.py
```

**新增 1 个运行时数据目录**：

```
data/processed/sessions/{user_id}.faiss
data/processed/sessions/{user_id}.meta.jsonl
```

**新增 SQLite 表**：`user_facts`（agent_sessions.sqlite 里）。

---

## 十二、收尾原则

做完这套方案，AIroute 就具备完整的 **working / episodic / semantic / vector** 四层记忆能力（procedural memory 不做），技术深度上对齐 Mem0 / Letta / LangGraph 之类 agent memory 框架的核心思路，且全部基于已有的 FAISS + SQLite 基建复用，没引入新的存储依赖。

按以下三条优先级排序解决冲突：

1. **A → B → C → D 顺序不能跳**。Schema 不齐时下层模块编译都通不过；情景记忆是语义记忆的数据源；语义记忆是向量记忆的特征源。
2. **每阶段必须先跑测试再 commit**。三层记忆容易引入数据污染（譬如 facts cache 没失效、向量索引脏数据），测试是唯一防线。
3. **D 阶段可以单独裁剪**。如果时间紧到只剩两天，可以做完 A+B+C 把 D 推后——三层减到两层在简历上仍然能写 "episodic + semantic memory"，是合理的最小可用版。

4 天后，AIroute 就从"多 Agent + RAG"升级到"多 Agent + RAG + 三层 Memory"的完整 agent 系统形态。

# AIroute 复杂度升级与工程化改造方案

> 目标：把 AIroute 从「规则内核 + AI 外壳的黑客松 Demo」升级为「有 Agent 决策、有学习排序、有约束优化、且能用指标证明效果」的可信系统。
>
> 本轮范围：**不含**实时信号驱动（天气 / 实时路况 / 实时排队 / 外部事件驱动重规划）。其余方向全部纳入。
>
> 文档级别：含代码骨架（模块改动清单 + 关键接口/数据结构 + 伪代码/代码片段），可直接照着开工。

---

## 0. 怎么用这份文档

每个工作项（Work Package, WP）按统一结构组织：

- **动机 / 为什么加分**：说明这一项体现的是哪种工程/算法能力，为什么 reviewer 会认。
- **设计**：方案与关键取舍。
- **模块改动清单**：要改/新增哪些真实文件（路径与现仓库一致）。
- **关键接口 / 数据结构**：新增的 schema、service 契约。
- **代码骨架**：可直接落地的伪代码或片段。
- **验收指标**：怎么证明「做到了」。
- **工作量**：以「人·天」粗估（单人，含测试）。

工作量估算口径：1 人·天 ≈ 6 小时有效编码 + 测试。估算偏保守，方便排期留 buffer。

---

## 1. 现状基线与差距总览

### 1.1 现状架构（实测）

```
前端 (React + Vite, 移动优先, 6 页面)
  DiscoveryFeed / TripHome / TripCreate / RecommendPool / TripDetail / PlanResult
        │  REST
        ▼
FastAPI 后端
  api/            routes_plan / routes_pool / routes_trips / routes_onboarding / routes_preferences
  services/       orchestrator(薄分发) → plan_service → intent_service / solver_service /
                  poi_scoring_service / retrieval_service / route_validator / route_repairer /
                  route_replanner / chat_service / preference_service / ugc_service ...
  solver/         ordering(NN + 2-opt) / distance(haversine + 高德实路网) / styles
  llm/            client(OpenAI 兼容, 仅用于 intent) / embedding
  repositories/   sqlite_poi_repo / rag_index(Chroma) / trip_store / vector_repo
  state.py        进程内 dict: PLAN_REGISTRY / POOL_REGISTRY / ...
skills/           6 份 agent 设计文档(SKILL.md), 作为 system prompt 注入
```

### 1.2 能力定位

| 维度 | 现状 | 评价 |
| --- | --- | --- |
| 检索 | Chroma 向量库 + embedding + provenance + evidence，按开关降级 | ✅ 真 RAG，行业水准 |
| 路线排序 | 最近邻 + 2-opt 开放式 TSP（`solver/ordering.py`） | 🟡 真启发式，但目标单一 |
| 地图 | 高德实路网腿 + haversine 兜底（`solver/distance.py`） | ✅ 真集成 |
| 可解释性 | `score_breakdown` / `why_this_one` / dropped reasons / tradeoffs | ✅ 强项 |
| 鲁棒性 | 处处确定性 fallback（无 key 可跑） | ✅ Demo 友好 |
| LLM 使用 | 仅 `intent_service` 做需求理解 | 🔴 AI 太浅 |
| 对话改写 | `chat_service._detect_intent` 中文关键字 if-else | 🔴 最丢分 |
| 评分 | 手调魔数权重（`poi_scoring_service.py`） | 🔴 非数据驱动 |
| 优化目标 | 仅最小化通行时间，时间窗/营业时间未进优化器 | 🔴 与所引论文不符 |
| 状态 | 进程内 dict（`state.py`） | 🔴 不可持久/并发 |
| 评测 | 无任何指标 | 🔴 Demo 与可信系统的分水岭 |

### 1.3 差距与优先级总览

| WP | 名称 | 解决的核心问题 | 优先级 |
| --- | --- | --- | --- |
| WP-1 | 对话改写 → LLM function-calling | 拔掉最丢分的关键字逻辑 | P0 |
| WP-6 | 离线评测 harness | 拿到「可信度门票」 | P0 |
| WP-7 | LLM 可观测性与缓存 | 成本/延迟/降级可控 | P0 |
| WP-4 | 优化 → 带时间窗定向越野 (OPTW) | 算法深度 | P1 |
| WP-3 | 评分 → learning-to-rank | 数据驱动 | P1 |
| WP-5 | 多目标 Pareto 前沿 | 严谨且亮眼 | P1 |
| WP-2 | 规划编排 → plan-act-observe Agent | 让「Agent」名副其实 | P1 |
| WP-8 | 状态落库 + 行程版本树 | 工程化/多用户 | P2 |
| WP-9 | 蒙特卡洛鲁棒性模拟 | 差异化亮点 | P2 |
| WP-10 | 多人组团偏好聚合 | 差异化亮点 | P2 |

---

## 2. 升级总蓝图与里程碑

```
M1 拿门票 (P0)        WP-1 ──► WP-7 ──► WP-6
                       function-calling  可观测   评测harness
                              │
M2 算法深度 (P1)       WP-4 ──► WP-5         WP-3
                       OPTW    Pareto       LTR评分(可并行)
                              │
M3 Agent 真实性 (P1)   WP-2 plan-act-observe(依赖 WP-1 的工具定义 + WP-7 trace)
                              │
M4 工程化/差异化 (P2)  WP-8 状态落库 ──► WP-9 蒙特卡洛 ──► WP-10 组团聚合
```

依赖关系要点：

- WP-2（Agent 循环）复用 WP-1 定义的「工具」（tools）和 WP-7 的 trace，因此放在它们之后。
- WP-5（Pareto）建立在 WP-4（统一的目标函数/约束模型）之上。
- WP-3（LTR）可与 WP-4 并行：LTR 产出每个 POI 的 utility，正好作为 WP-4 定向越野的「奖励值」。
- WP-9（蒙特卡洛）需要 WP-4 的可行性校验逻辑作为单次评估器。

---

## 3. 工作项详述

### WP-1 · 对话改写：关键字 if-else → LLM function-calling + 槽位填充

**动机 / 为什么加分**
当前 `chat_service._detect_intent` 用 `"下雨" / "省钱" / "快"` 这类中文子串匹配判断用户改写意图，这是 reviewer 一眼判定「AI 外壳、规则内核」的地方。换成 LLM 结构化工具调用后，系统具备真正的自然语言理解、可处理同义/复合/否定表达，并产出**带类型、带置信度、可校验、可二次确认**的动作，这是「对话式规划」的及格线。

**设计**
- 定义一组**类型化改写动作（Tool / Action）**，LLM 只能从中选择并填槽，杜绝自由发挥。
- LLM 返回 `action + slots + confidence + rationale`；低置信度走澄清确认环。
- 保留现有 `RouteReplanner` 作为「执行器」——LLM 只负责「决定做什么」，执行仍走确定性代码，安全可控。
- 无 key / 解析失败时回退到现有关键字逻辑（保留它做 fallback，不删）。

**模块改动清单**
- 改：`backend/app/services/chat_service.py`（`_detect_intent` 改为调用新的 `ReplanIntentParser`，关键字逻辑降级为 fallback）。
- 新增：`backend/app/services/replan_intent_parser.py`。
- 新增：`backend/app/schemas/replan_action.py`（动作枚举与槽位 schema）。
- 复用：`backend/app/llm/client.py` 的 `complete_json`（已支持 OpenAI 兼容 + fallback）。
- 改：`backend/app/services/route_replanner.py`（接收结构化 `ReplanAction` 而非裸 `event_type`）。
- 测试：`backend/tests/test_replan_intent_parser.py`（含同义/复合/否定/低置信度用例）。

**关键接口 / 数据结构**

```python
# backend/app/schemas/replan_action.py
from enum import Enum
from pydantic import BaseModel, Field

class ReplanActionType(str, Enum):
    REPLACE_STOP        = "replace_stop"        # 替换某站
    DROP_STOP           = "drop_stop"           # 删除某站
    ADD_CATEGORY        = "add_category"        # 加一类（如加咖啡）
    COMPRESS_TIME       = "compress_time"       # 压缩到 N 小时
    LOWER_BUDGET        = "lower_budget"        # 降预算 / 更便宜
    AVOID_QUEUE         = "avoid_queue"         # 少排队
    PREFER_INDOOR       = "prefer_indoor"       # 改室内（雨天等，仍属用户主动指令）
    ASK_WHY             = "ask_why"             # 解释理由
    UNKNOWN             = "unknown"

class ReplanSlots(BaseModel):
    target_stop_index: int | None = None
    replacement_poi_id: str | None = None
    target_category: str | None = None
    time_budget_min: int | None = None
    budget_total: int | None = None

class ReplanAction(BaseModel):
    action: ReplanActionType
    slots: ReplanSlots = Field(default_factory=ReplanSlots)
    confidence: float = 0.0          # 0~1
    rationale: str = ""              # 一句话证据，用于可解释
    needs_confirmation: bool = False
```

**代码骨架**

```python
# backend/app/services/replan_intent_parser.py
from app.llm.client import LlmClient
from app.schemas.replan_action import ReplanAction, ReplanActionType, ReplanSlots

CONFIRM_THRESHOLD = 0.55

class ReplanIntentParser:
    def parse(self, message: str, plan, action_type: str | None = None) -> ReplanAction:
        # 1) 前端显式动作优先（如点了"替换"按钮），跳过 LLM
        if action_type == "replace_stop":
            return ReplanAction(action=ReplanActionType.REPLACE_STOP, confidence=1.0)

        # 2) 构造 fallback：复用旧关键字逻辑，保证无 key 也能跑
        fallback = self._keyword_fallback(message)

        # 3) LLM 结构化解析（function-calling 风格的 JSON 输出）
        prompt = self._build_prompt(message, plan)
        data = LlmClient().complete_json(
            prompt, fallback.model_dump(), agent_name="replan",
        )
        try:
            action = ReplanAction.model_validate(data)
        except Exception:
            return fallback

        action.needs_confirmation = action.confidence < CONFIRM_THRESHOLD
        return action

    def _build_prompt(self, message: str, plan) -> str:
        stops = [{"index": i, "name": s.poi_name, "category": s.category}
                 for i, s in enumerate(plan.stops)]
        return f"""把用户的改写诉求解析为一个 ReplanAction JSON。只能从给定 action 枚举中选一个，并填写相关 slots；无法确定的 slot 用 null。
当前路线站点：{stops}
action 取值：replace_stop / drop_stop / add_category / compress_time / lower_budget / avoid_queue / prefer_indoor / ask_why / unknown
要求：给出 0~1 的 confidence 和一句话 rationale。
用户输入：{message}
"""

    def _keyword_fallback(self, message: str) -> ReplanAction:
        # 把现有 chat_service._detect_intent 的关键字规则平移到这里，作为降级
        ...
```

`chat_service.adjust_plan` 改为：先 `ReplanIntentParser().parse(...)` 得到 `ReplanAction`，若 `needs_confirmation` 则返回澄清问句；否则把结构化动作交给 `RouteReplanner` 执行。

**验收指标**
- 在一组 ≥ 40 条改写话术的标注集上，动作分类准确率 ≥ 0.9（vs 旧关键字基线，给出对比数字）。
- 复合/否定话术（如「别太赶但也别太贵」）能正确产出多槽位或触发澄清。
- 无 key 时自动降级、功能不挂。

**工作量**：2.5 人·天

---

### WP-7 · LLM 可观测性、缓存与降级 SLO

> 提前到 P0，因为 WP-1/WP-2 都会放大 LLM 调用量，没有 trace 和缓存就无法定位问题、控制成本。

**动机 / 为什么加分**
「能调通 LLM」和「能运营 LLM」是两回事。trace、token 成本、延迟、缓存命中率、降级率——这些是大厂判断你是否真做过线上 LLM 应用的硬指标。

**设计**
- 在 `LlmClient` 外包一层装饰：记录每次调用的 `agent_name / model / prompt_hash / tokens / latency_ms / status(success|fallback|error)`。
- 加 **请求级缓存**：对 `(prompt_hash, model)` 做 LRU/SQLite 缓存（intent、replan 解析这类幂等调用收益最大）。
- 暴露 `/metrics`（Prometheus 文本格式）或最简版 `/debug/llm_stats` JSON。
- 定义降级 SLO：LLM p95 延迟 / fallback 率 阈值，超阈值告警（先打日志即可）。

**模块改动清单**
- 改：`backend/app/llm/client.py`（注入 `LlmTelemetry` + `LlmCache`）。
- 新增：`backend/app/llm/telemetry.py`、`backend/app/llm/cache.py`。
- 新增：`backend/app/api/routes_debug.py`（`/debug/llm_stats`）。
- 测试：`backend/tests/test_llm_cache.py`（命中/未命中、降级计数）。

**关键接口 / 代码骨架**

```python
# backend/app/llm/telemetry.py
import time, hashlib, logging
from dataclasses import dataclass, field

logger = logging.getLogger("llm.telemetry")

@dataclass
class LlmCallRecord:
    agent_name: str
    model: str
    prompt_hash: str
    latency_ms: int
    status: str           # success | fallback | error | cache_hit
    prompt_tokens: int = 0
    completion_tokens: int = 0

@dataclass
class LlmTelemetry:
    records: list[LlmCallRecord] = field(default_factory=list)
    def record(self, r: LlmCallRecord):
        self.records.append(r)
        logger.info("llm_call agent=%s status=%s lat=%dms tok=%d/%d",
                    r.agent_name, r.status, r.latency_ms, r.prompt_tokens, r.completion_tokens)
    def stats(self) -> dict:
        n = len(self.records) or 1
        lat = sorted(r.latency_ms for r in self.records)
        p95 = lat[int(len(lat) * 0.95) - 1] if lat else 0
        fb = sum(1 for r in self.records if r.status in {"fallback", "error"})
        hit = sum(1 for r in self.records if r.status == "cache_hit")
        return {"calls": len(self.records), "p95_latency_ms": p95,
                "fallback_rate": round(fb / n, 3), "cache_hit_rate": round(hit / n, 3)}

def prompt_hash(model: str, system: str, prompt: str) -> str:
    return hashlib.sha256(f"{model}\n{system}\n{prompt}".encode()).hexdigest()[:16]
```

在 `LlmClient.complete_json` 里：先查 `LlmCache`，命中记 `cache_hit` 直接返回；未命中正常调用，`time.perf_counter()` 计时，按 `status` 记录 telemetry，并写入缓存。

**验收指标**
- `/debug/llm_stats` 能给出 calls / p95 延迟 / fallback 率 / 缓存命中率。
- 对重复 intent 解析，缓存命中率 > 80%，端到端延迟下降可量化。

**工作量**：1.5 人·天

---

### WP-6 · 离线评测 Harness：指标体系 + 解释忠实度自动化

**动机 / 为什么加分**
这是 Demo 与可信系统之间最大的分水岭，也是「业内认可」的门票。绝大多数黑客松项目说不出「我的路线好在哪、好多少」。一旦你能给出可复现的指标和基准集，叙事就从「能演」变成「可信」。

**设计**
- 建一组**场景基准集**（YAML/JSON）：每条 = 一份 `PlanRequest` + 期望约束（时间窗、预算、必含类目、must-visit）。覆盖 paper-insights 里的演示场景（半日游 / 情侣夜游 / 家庭雨天）。
- 跑 pipeline 产出路线，自动算下列指标：

| 指标 | 含义 | 怎么算 |
| --- | --- | --- |
| 约束满足率 | 硬约束（时间窗/预算/必含/必到）满足比例 | 复用 `RouteValidator` |
| 路线可行率 | 能产出合法路线的请求比例 | pipeline 成功率 |
| 通行时间最优性 gap | 相对 OR-Tools 精确解的差距 | (启发式解 − 最优解)/最优解 |
| 个性化命中率 | liked POI 进入路线/备选的比例 | 对 `preference_snapshot` 统计 |
| 多样性 | 路线间类目/POI 重叠度 | 1 − Jaccard |
| **解释忠实度** | `why_this_one` 的论据是否真匹配 POI/评分/UGC | 见下 |

- **解释忠实度自动化**：你们 `route-planning-agent/SKILL.md` 已写「Explanation facts match POI attributes」这条 validation 规则——把它变成自动检查：解析 `why_this_one` 中引用的关键词/分数，回查 `score_breakdown`、`poi.high_freq_keywords`、`poi.category` 是否一致，输出忠实度得分。

**模块改动清单**
- 新增目录：`eval/`
  - `eval/scenarios/*.yaml`（基准场景集）
  - `eval/metrics.py`（各指标实现）
  - `eval/run_eval.py`（批量跑 + 出报告）
  - `eval/report_template.md`（结果汇总模板）
- 复用：`RouteValidator`、`PlanService`、（WP-4 后）OR-Tools 精确解作为 oracle。
- CI：在 `.github/workflows/eval.yml` 跑评测并把关键指标作为 PR gate（回归即红）。

**关键数据结构 / 代码骨架**

```python
# eval/metrics.py
from dataclasses import dataclass

@dataclass
class EvalResult:
    scenario_id: str
    constraints_satisfied: bool
    feasible: bool
    travel_time_gap: float | None      # 相对最优解
    personalization_hit: float
    diversity: float
    explanation_faithfulness: float

def explanation_faithfulness(plan) -> float:
    ok, total = 0, 0
    for stop in plan.stops:
        total += 1
        claims = extract_claims(stop.why_this_one)        # 解析"评分依据/UGC 高频提到 X"
        if claims_match_evidence(claims, stop.score_breakdown, stop):
            ok += 1
    return ok / max(total, 1)
```

```python
# eval/run_eval.py  (命令行: python -m eval.run_eval --out eval/report.md)
def main():
    scenarios = load_scenarios("eval/scenarios")
    results = [evaluate(s) for s in scenarios]
    summary = aggregate(results)   # 各指标均值/分布
    write_markdown_report(summary, results, "eval/report.md")
    assert summary["constraint_satisfaction_rate"] >= 0.95  # CI gate 示例
```

**验收指标**
- `python -m eval.run_eval` 一键产出 `eval/report.md`，含上表全部指标的数字。
- 建立基线后，后续每个 WP 都能在同一基准集上「跑出 before/after 对比」。
- 解释忠实度 ≥ 0.95（说明可解释性不是编的）。

**工作量**：3 人·天（首次建集 + 指标实现）

---

### WP-3 · POI 评分：手调魔数 → Learning-to-Rank

**动机 / 为什么加分**
`poi_scoring_service.py` 现在是一堆 `+7 / -16 / /20` 的拍脑袋权重。换成可训练的排序模型后，「评分是学出来的」就成立——这是「规则系统」到「AI 系统」的本质跨越。而且你们的 `ScoreBreakdown` 契约和 paper-insights 早就为「插模型」留好了口子（I-AIR 的多信号抽象）。

**设计**
- 把现有手工分项**保留为特征**，不丢弃：`user_interest / poi_quality / context_fit / ugc_match / service_closure / history_preference` + UGC 向量相似度 + 距离 + 排队 + co-visit/popularity。
- 训练 **LambdaMART（LightGBM ranker）**：候选集排序问题，pairwise/listwise 目标天然契合。
- **标签来源**（无真实点击日志时的弱监督）：用 `preference_snapshot`（liked=正、disliked=负）+ 规则分高位作为伪正例 + 随机负采样，先把 pipeline 跑通；接入真实日志后无缝替换。
- 产出仍填回 `ScoreBreakdown.total`，对下游（solver/alternatives）零侵入——只是 `total` 从「加和」变「模型打分」。

**模块改动清单**
- 新增：`backend/app/ml/ranker.py`（加载模型 + 预测）、`backend/app/ml/features.py`（特征抽取，复用现有分项）。
- 新增：`scripts/train_ranker.py`（造弱标签 + 训练 + 导出 `data/models/ranker.txt`）。
- 改：`backend/app/services/poi_scoring_service.py`（`total` 改为 `ranker.predict(features)`，分项继续返回用于解释；模型缺失时回退到原加和公式）。
- 依赖：`lightgbm`（加入 backend 依赖）。
- 测试：`backend/tests/test_ranker.py`（特征维度、缺模型降级、单调性 sanity）。

**代码骨架**

```python
# backend/app/ml/features.py
FEATURE_ORDER = [
    "user_interest", "poi_quality", "context_fit", "ugc_match",
    "service_closure", "history_preference", "queue_min", "price",
    "distance_m", "ugc_sim", "popularity",
]

def build_features(poi, breakdown, ctx) -> list[float]:
    return [
        breakdown.user_interest, breakdown.poi_quality, breakdown.context_fit,
        breakdown.ugc_match, breakdown.service_closure, breakdown.history_preference,
        poi.queue_estimate["weekend_peak"], poi.price_per_person or 0.0,
        ctx.distance_m or 0.0, ctx.ugc_sim or 0.0, float(poi.review_count or 0),
    ]
```

```python
# backend/app/ml/ranker.py
import lightgbm as lgb
from pathlib import Path

class PoiRanker:
    def __init__(self, model_path="data/models/ranker.txt"):
        self.model = lgb.Booster(model_file=model_path) if Path(model_path).exists() else None
    def predict(self, feats: list[float]) -> float | None:
        if self.model is None:
            return None                      # 让调用方回退到旧加和公式
        return float(self.model.predict([feats])[0])
```

```python
# poi_scoring_service.py  末尾改造
raw_total = (user_interest + poi_quality + ... + risk_penalty)   # 旧公式保留为 fallback
model_score = self.ranker.predict(build_features(poi, partial_breakdown, ctx))
total = model_score if model_score is not None else raw_total
```

**验收指标**
- 在 WP-6 基准集上，个性化命中率 / NDCG@5 相对旧公式有可量化提升（给出 before/after）。
- 模型文件缺失时自动降级，线上不挂。

**工作量**：3 人·天（含造数与训练脚本）

---

### WP-4 · 路线优化：贪心 + 2-opt → 带时间窗的定向越野 (OPTW)

**动机 / 为什么加分**
现在 `solver_service` 是「按 style 打分取 top-N + 2-opt 调顺序」，只最小化通行时间，营业时间/时间窗都没作为硬约束进优化器。你们引用的 PersTour / OPTW 论文说的正是**带时间窗的定向越野问题**：在时间预算内，从一堆带「奖励值」的点里选一个子集并排序，**最大化总奖励**，同时满足时间窗、营业时间、预算、must-visit。这是能写进简历、能和精确解比 gap 的真算法升级。

**设计**
- 形式化：
  - 变量：选哪些 POI、访问顺序、各点到达时间。
  - 目标：最大化 Σ utility（utility 来自 WP-3 的排序分）。
  - 约束：总时长 ≤ 时间预算；每点到达时间 ∈ 营业时间窗；Σ 花费 ≤ 预算；must-visit 必选；类目覆盖。
- 两档求解器（按候选规模自动切换）：
  - **精确**：OR-Tools CP-SAT（候选 ≤ ~15），用作 oracle 与小规模生产解。
  - **元启发式**：ALNS / 迭代局部搜索（候选更大时），与 paper-insights 的 ILS 对齐。
- 现有 `route_repairer` / `route_validator` 自然成为「约束校验器」与「破坏-修复算子」的一部分。

**模块改动清单**
- 新增：`backend/app/solver/optw.py`（OPTW 建模 + CP-SAT 求解）、`backend/app/solver/alns.py`（元启发式）。
- 改：`backend/app/services/solver_service.py`（`_solve_style` 改为调用 OPTW，按规模选求解器；style 退化为「目标权重/锚点配置」）。
- 复用：`solver/distance.py`（腿时间矩阵）、`route_validator.py`（约束）。
- 依赖：`ortools`。
- 测试：`backend/tests/test_optw.py`（时间窗违例为 0、must-visit 必含、与暴力最优解一致性）。

**关键数据结构 / 代码骨架**

```python
# backend/app/solver/optw.py
from dataclasses import dataclass
from ortools.sat.python import cp_model

@dataclass
class OptwNode:
    poi_id: str
    utility: float                 # 来自 WP-3 ranker
    visit_min: int                 # 停留+排队
    open_min: int                  # 营业开始(分钟)
    close_min: int                 # 营业结束(分钟)
    price: float

def solve_optw(nodes, travel, *, start_min, end_min, budget,
               must_visit: set[str]) -> list[str]:
    """返回有序 poi_id 列表，最大化总 utility，满足时间窗/预算/必到。"""
    model = cp_model.CpModel()
    n = len(nodes)
    x = [model.NewBoolVar(f"x{i}") for i in range(n)]            # 是否选
    t = [model.NewIntVar(start_min, end_min, f"t{i}") for i in range(n)]  # 到达时间
    y = {(i, j): model.NewBoolVar(f"y{i}_{j}")                   # 顺序边
         for i in range(n) for j in range(n) if i != j}

    for i, node in enumerate(nodes):
        model.Add(t[i] >= node.open_min).OnlyEnforceIf(x[i])
        model.Add(t[i] + node.visit_min <= node.close_min).OnlyEnforceIf(x[i])
        if node.poi_id in must_visit:
            model.Add(x[i] == 1)
    # 预算
    model.Add(sum(int(nodes[i].price) * x[i] for i in range(n)) <= int(budget))
    # 顺序时序：选中 i->j 则 t[j] >= t[i] + visit_i + travel_ij
    for (i, j), yij in y.items():
        model.Add(t[j] >= t[i] + nodes[i].visit_min + travel[i][j]).OnlyEnforceIf(yij)
    # 流约束（每个选中点入度=出度=1，开放路径）... 省略
    model.Maximize(sum(int(nodes[i].utility * 100) * x[i] for i in range(n)))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 3.0
    solver.Solve(model)
    return _extract_order(solver, x, t, nodes)
```

**验收指标**
- 时间窗 / 营业时间违例数 = 0（旧版本无此约束，给出对比）。
- 候选 ≤ 12 时，CP-SAT 解 = 暴力最优；启发式相对最优 gap < 5%。
- WP-6 报告里「约束满足率」「通行时间 gap」明显改善。

**工作量**：4 人·天

---

### WP-5 · 路线风格：三个手命名 style → 多目标 Pareto 前沿

**动机 / 为什么加分**
现在 `efficient / relaxed / foodie_first` 是硬编码三套 + 手写 highlights/tradeoffs。改成在「时间 × 花费 × 排队 × 兴趣」上求**帕累托前沿**，既更严谨（每条路线都是某个权衡下的非支配解），又更亮眼（可视化前沿让用户在权衡上自己选），还能自然解释 tradeoff（A 比 B 省 ¥X 但多花 Y 分钟）。

**设计**
- 多次跑 WP-4 的 OPTW，对目标做不同加权（标量化），或直接做多目标进化（NSGA-II），收集非支配解集。
- 前端在前沿上展示 3~5 个代表性方案，tradeoff 文案由「两解之间的指标差」自动生成，替代现在的手写 `_tradeoffs`。

**模块改动清单**
- 新增：`backend/app/solver/pareto.py`（标量化扫描 / NSGA-II + 非支配过滤）。
- 改：`backend/app/services/solver_service.py`（`solve` 返回前沿上的代表解而非固定三 style）。
- 改：`backend/app/services/plan_service.py`（`_style_highlights / _tradeoffs` 改为按指标差自动生成）。
- 改：前端 `PlanCompare.tsx`（可加一个 2D 前沿散点：x=花费, y=时间, 点大小=兴趣）。
- 测试：`backend/tests/test_pareto.py`（返回解互不支配、覆盖度）。

**代码骨架**

```python
# backend/app/solver/pareto.py
def dominates(a: dict, b: dict) -> bool:
    """a 在所有目标上不差于 b，且至少一个更优。目标：min 时间/花费/排队, max 兴趣。"""
    better_or_equal = (a["time"] <= b["time"] and a["cost"] <= b["cost"]
                       and a["queue"] <= b["queue"] and a["interest"] >= b["interest"])
    strictly_better = (a["time"] < b["time"] or a["cost"] < b["cost"]
                       or a["queue"] < b["queue"] or a["interest"] > b["interest"])
    return better_or_equal and strictly_better

def pareto_front(solutions: list[dict]) -> list[dict]:
    return [s for s in solutions if not any(dominates(o, s) for o in solutions if o is not s)]

def representative(front: list[dict], k: int = 3) -> list[dict]:
    """从前沿挑 k 个代表解：偏省钱 / 偏省时 / 折中。"""
    ...
```

**验收指标**
- 返回的方案集互不支配（自动断言）。
- tradeoff 文案与指标差一致（不再是写死的话术）。

**工作量**：2.5 人·天

---

### WP-2 · 规划编排：薄分发器 → plan-act-observe Agent 循环

**动机 / 为什么加分**
现在 `orchestrator.py` 只是把请求转给各 service，没有任何「决策」。要让「Agent」名副其实，需要一个 LLM 驱动的 **plan → act → observe → replan** 循环：LLM 看到当前状态后**自己决定下一步调哪个工具**，观察结果（如校验失败、预算超了），再决定补救动作，直到产出可行计划或触达步数预算。这是对「AI 应用工程师」这个受众单点收益最大的升级。

**设计**
- 把现有 service 包装成**工具（Tool）**：`retrieve_pois / score_pois / solve_route / validate_route / repair_route / explain_plan`（注意：本轮不含实时信号类工具）。
- LLM 用 function-calling 在工具间编排；每步把 `AgentRunState`（你们 `state.py` 已有雏形）喂回去。
- **强约束安全**：工具白名单 + 最大步数预算 + 每步结果校验；任何时候都能用 WP-4 的确定性 pipeline 作为「保底执行」。LLM 负责「编排与补救策略」，不负责直接造路线。
- 复用 WP-7 的 trace：每步 act/observe 全程可观测。

**模块改动清单**
- 新增：`backend/app/agent/harness.py`（循环控制器）、`backend/app/agent/tools.py`（工具注册表 + schema）。
- 改：`backend/app/services/orchestrator.py`（`generate_plans` 可选走 harness；默认仍走确定性 pipeline，feature flag 控制）。
- 复用：`state.py` 的 `AgentRunState`（补 `steps: list[AgentStep]`）。
- 测试：`backend/tests/test_agent_harness.py`（步数预算、非法工具拒绝、校验失败后能补救）。

**关键数据结构 / 代码骨架**

```python
# backend/app/agent/tools.py
from pydantic import BaseModel

class ToolSpec(BaseModel):
    name: str
    description: str
    args_schema: dict          # JSON schema, 给 LLM function-calling 用

TOOLS = {
    "retrieve_pois":  ToolSpec(name="retrieve_pois",  description="按需求检索候选 POI", args_schema={...}),
    "score_pois":     ToolSpec(name="score_pois",     description="对候选打分", args_schema={...}),
    "solve_route":    ToolSpec(name="solve_route",    description="求解 OPTW 路线", args_schema={...}),
    "validate_route": ToolSpec(name="validate_route", description="校验硬约束", args_schema={...}),
    "repair_route":   ToolSpec(name="repair_route",   description="修复违例", args_schema={...}),
    "explain_plan":   ToolSpec(name="explain_plan",   description="生成可解释理由", args_schema={...}),
}
```

```python
# backend/app/agent/harness.py
MAX_STEPS = 8

class PlanningHarness:
    def run(self, request, run_state) -> "RefinedPlan":
        for step in range(MAX_STEPS):
            decision = self._ask_llm_next_action(run_state)      # -> {tool, args} 或 {finish}
            if decision.get("finish"):
                break
            tool, args = decision["tool"], decision["args"]
            if tool not in TOOLS:                                # 白名单
                run_state.steps.append(AgentStep(tool=tool, status="rejected"))
                continue
            observation = self._invoke(tool, args, run_state)    # 调真实 service
            run_state.steps.append(AgentStep(tool=tool, status="ok", observation=observation))
            if self._goal_satisfied(run_state):                  # 校验通过即可结束
                break
        return self._finalize_or_fallback(run_state)             # 失败则回退确定性 pipeline
```

**验收指标**
- 在 WP-6 基准集上，harness 路径的约束满足率 ≥ 确定性 pipeline（不能更差），且能展示「校验失败 → 自动补救 → 通过」的多步 trace。
- 步数预算、非法工具、超时都有保护，无死循环。

**工作量**：4 人·天

---

### WP-8 · 状态落库：进程内 dict → 持久化 + 用户会话隔离 + 行程版本树

**动机 / 为什么加分**
`state.py` 用 `PLAN_REGISTRY` 等进程内 dict 存方案：单进程、重启即丢、多用户会串。这是 reviewer 一眼能看穿的「玩具」特征。落库 + 会话隔离 + 版本化是「能上线」的基本门槛，而你们已有 `save_route_version`，顺势做成行程版本树即可。

**设计**
- 用现成的 `app_state.sqlite`（config 里已配 `app_state_sqlite_path`）或 Postgres（`database_url` 已配）存：plan / context / profile / preference / pool。
- 所有 registry 访问改为走 repository，key 带 `user_id` / `session_id` 做隔离。
- 行程版本树：每次 replan 生成新版本，父指针指向上一版，支持「回到上一版」。

**模块改动清单**
- 改：`backend/app/services/state.py`（`*_REGISTRY` 改为薄包装，背后走 repo）。
- 新增：`backend/app/repositories/plan_store.py`（plan/context/profile 持久化，复用 `trip_store.py` 的 sqlite 模式）。
- 改：`backend/app/repositories/trip_store.py`（行程版本树：`parent_version_id` 字段）。
- 改：所有 `PLAN_REGISTRY[...]` 直接访问点（`plan_service.py` / `chat_service.py`）。
- 测试：`backend/tests/test_plan_store.py`（持久化往返、会话隔离、版本回溯）。

**代码骨架**

```python
# backend/app/repositories/plan_store.py
import json, sqlite3

class PlanStore:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("""CREATE TABLE IF NOT EXISTS plans(
            plan_id TEXT PRIMARY KEY, session_id TEXT, user_id TEXT,
            payload TEXT, parent_version_id TEXT, created_at TEXT)""")

    def save(self, plan, *, session_id, user_id, parent=None):
        self.conn.execute(
            "INSERT OR REPLACE INTO plans VALUES (?,?,?,?,?,datetime('now'))",
            (plan.plan_id, session_id, user_id, plan.model_dump_json(), parent))
        self.conn.commit()

    def get(self, plan_id, *, session_id):
        row = self.conn.execute(
            "SELECT payload FROM plans WHERE plan_id=? AND session_id=?",
            (plan_id, session_id)).fetchone()
        return RefinedPlan.model_validate_json(row[0]) if row else None
```

**验收指标**
- 服务重启后历史方案/行程可恢复。
- 两个 `session_id` 互不可见（隔离测试通过）。
- 能从 v3 回退到 v2 并继续 replan。

**工作量**：3 人·天

---

### WP-9 · 蒙特卡洛鲁棒性模拟（差异化亮点）

**动机 / 为什么加分**
给排队和腿时间加随机扰动，对一条路线模拟成百上千次「一整天」，统计「按时完成概率 / 期望超时 / P90 总时长」，输出**路线的鲁棒性评分**。这呼应不确定性下的 orienteering，是个既硬核又好讲的差异化点：你不只给路线，还给「这条路线有多稳」。注意——这是**对静态分布做蒙特卡洛**，不是接实时信号，符合本轮范围。

**设计**
- 为每条腿时间和每个排队时长定义分布（用现有 `queue_estimate` 做均值，加一个变异系数；可后续用历史数据标定）。
- 对一条已生成路线做 N 次采样，每次用 WP-4 的可行性逻辑判断是否按时完成。
- 输出 `on_time_prob / expected_overflow_min / p90_total_min`，并可用于在 Pareto 前沿里给「稳」的方案加权。

**模块改动清单**
- 新增：`backend/app/sim/montecarlo.py`。
- 改：`backend/app/schemas/plan.py`（`PlanSummary` 加 `robustness` 字段）。
- 改：`backend/app/services/plan_service.py`（`_refine_one` 末尾算 robustness）。
- 改：前端 `PlanTimeline.tsx`（展示「准时概率 92%」徽标）。
- 测试：`backend/tests/test_montecarlo.py`（确定性种子下结果可复现）。

**代码骨架**

```python
# backend/app/sim/montecarlo.py
import random

def simulate(plan, *, n=500, seed=42, cv=0.3) -> dict:
    rng = random.Random(seed)
    end_min = to_min(plan_window_end(plan))
    overflows, on_time = [], 0
    for _ in range(n):
        t = to_min(plan.stops[0].arrival_time)
        for stop in plan.stops:
            queue = max(0, rng.gauss(stop.estimated_queue_min, stop.estimated_queue_min * cv))
            t += stop_visit_min(stop) + queue
            if stop.transport_to_next:
                leg = stop.transport_to_next.duration_min
                t += max(1, rng.gauss(leg, leg * cv))
        overflow = max(0, t - end_min)
        overflows.append(overflow)
        on_time += (overflow == 0)
    overflows.sort()
    return {"on_time_prob": round(on_time / n, 3),
            "expected_overflow_min": round(sum(overflows) / n, 1),
            "p90_total_min": overflows[int(n * 0.9) - 1]}
```

**验收指标**
- 固定种子下结果可复现。
- 「准时概率」能区分出明显更稳/更险的两条路线（给对比例子）。

**工作量**：2 人·天

---

### WP-10 · 多人组团偏好聚合（差异化亮点）

**动机 / 为什么加分**
真实出行常是多人组团，每个人偏好不同。把「多用户偏好 → 一条大家都能接受的路线」建模成**偏好聚合 / 社会选择**问题，是个真正困难且有意思的方向，区分度极高。

**设计**
- 每个成员有自己的 `preference_snapshot`；聚合策略可选：
  - **均值效用**（最大化总满意度）。
  - **最大最小公平**（最大化最不满意成员的满意度，避免有人被牺牲）。
  - **否决权**：任一成员 disliked 的 POI 直接排除。
- 聚合后的「群体 utility」喂给 WP-4 的 OPTW 作为奖励值；输出里标注「此站为谁而选 / 谁的妥协」。

**模块改动清单**
- 新增：`backend/app/services/group_preference_service.py`。
- 改：`backend/app/schemas/preferences.py`（支持 `members: list[PreferenceSnapshot]`）。
- 改：`backend/app/api/routes_plan.py`（接收多成员偏好）。
- 改：前端 `TripCreatePage.tsx`（多人偏好录入）。
- 测试：`backend/tests/test_group_preference.py`（公平性：无成员满意度为 0；否决生效）。

**代码骨架**

```python
# backend/app/services/group_preference_service.py
from app.schemas.preferences import PreferenceSnapshot

class GroupPreferenceService:
    def aggregate_utility(self, poi, members: list[PreferenceSnapshot],
                          strategy="maxmin") -> float:
        utils = [self._member_utility(poi, m) for m in members]
        if any(poi.id in m.disliked_poi_ids for m in members):   # 否决权
            return -1e6
        if strategy == "mean":
            return sum(utils) / len(utils)
        return min(utils)                                        # maxmin 公平

    def _member_utility(self, poi, m: PreferenceSnapshot) -> float:
        u = m.category_weights.get(poi.category, 0.0) * 5
        u += 14 if poi.id in m.liked_poi_ids else 0
        for tag in poi.tags:
            u += m.tag_weights.get(tag, 0.0) * 1.2
        return u
```

**验收指标**
- maxmin 策略下，没有成员满意度为 0（公平性断言）。
- 否决权生效：任一成员 disliked 的 POI 不出现在路线。

**工作量**：3 人·天

---

## 4. 阶段化里程碑与排期

总工作量约 **28.5 人·天**（单人，含测试）。建议分 4 个里程碑推进，每个里程碑结束都在 WP-6 的同一基准集上跑一次 before/after。

| 里程碑 | 目标 | 工作项 | 小计(人·天) |
| --- | --- | --- | --- |
| **M1 拿门票** | 拔掉最丢分逻辑 + 建立可信度基础 | WP-1 + WP-7 + WP-6 | 7 |
| **M2 算法深度** | 真约束优化 + 学习排序 + 多目标 | WP-4 + WP-3 + WP-5 | 9.5 |
| **M3 Agent 真实性** | LLM 驱动的编排与补救 | WP-2 | 4 |
| **M4 工程化 + 差异化** | 落库 + 鲁棒性 + 组团 | WP-8 + WP-9 + WP-10 | 8 |

排期建议：

- **先 M1**。哪怕只做完 M1，叙事就已经从「能演的 demo」变成「有 NLU、有可观测、有指标」的系统——这是性价比最高的一段。
- M2 的 **WP-3（LTR）和 WP-4（OPTW）可并行**：LTR 的输出（utility）正好是 OPTW 的奖励值输入，两人协作时是天然分工。
- M3 依赖 M1 的工具定义与 trace，必须在 M1 之后。
- M4 任意时间可插入，WP-8 越早做越能减少后期返工（状态层是地基）。

如果时间非常紧（比如只有一周），优先级砍到：**WP-1 → WP-6 → WP-4**。这三件做完，「agent 决策的雏形 + 指标证明 + 真约束优化」三个最硬的卖点就齐了。

---

## 5. 风险与取舍

- **不要为复杂而复杂**。每个 WP 都要能回答「这体现了哪种能力、reviewer 为什么认」。WP-2（Agent 循环）尤其要克制：LLM 只做编排与补救，绝不让它直接造路线，否则会引入不可控和不可复现，反而扣分。
- **LLM 成本与延迟**。WP-1/WP-2 会放大调用量，所以把 WP-7（缓存 + trace）提前到 P0；intent / replan 这类幂等调用务必走缓存。
- **弱标签的局限**。WP-3 初期用 `preference_snapshot` 造弱标签，NDCG 提升幅度有限是正常的；重点是把「可训练 + 可替换真实日志」的管线搭起来，叙事价值大于初期精度。
- **OR-Tools 规模**。CP-SAT 在候选 > ~15 时求解时间会涨，务必设 `max_time_in_seconds` 并在超规模时切到 ALNS；用暴力最优解只在评测里当 oracle，不上生产。
- **保留确定性兜底**。现有「无 key 也能跑」是这个项目的优点，所有 WP 的改造都必须保留 fallback 路径，别把这个优点改没了。
- **改造顺序对测试的影响**。WP-8（状态落库）会触及很多 `*_REGISTRY` 访问点，越晚做返工越多；若人手够，可与 M1 并行先把状态层抽象出来。

---

## 6. 验收指标总表（基线 → 目标）

建立 WP-6 基准集后，用同一组场景持续追踪下列指标：

| 指标 | 现状(基线) | 目标 | 关联 WP |
| --- | --- | --- | --- |
| 改写意图分类准确率 | 关键字规则，无量化 | ≥ 0.90 | WP-1 |
| 硬约束满足率 | 部分（时间窗未进优化器） | ≥ 0.95 | WP-4 / WP-6 |
| 时间窗 / 营业时间违例数 | 未约束 | 0 | WP-4 |
| 通行时间相对最优 gap | 未知 | < 5% | WP-4 |
| 个性化命中率 / NDCG@5 | 手调公式 | 可量化提升 | WP-3 |
| 解释忠实度 | 未度量 | ≥ 0.95 | WP-6 |
| LLM p95 延迟 / 缓存命中率 | 无观测 | 可观测，命中 > 80% | WP-7 |
| 状态可恢复 / 会话隔离 | 进程内 dict | 重启可恢复，隔离通过 | WP-8 |
| 路线准时概率（鲁棒性） | 无 | 可输出并区分稳/险 | WP-9 |
| 组团公平性（无人满意度为 0） | 不支持组团 | 通过 | WP-10 |

---

## 附录 A · 依赖与技术选型

| 用途 | 选型 | 备注 |
| --- | --- | --- |
| 排序模型 | LightGBM (LambdaMART) | 候选排序，pairwise/listwise；可后续换神经排序器 |
| 约束优化 | OR-Tools CP-SAT | 精确解 / 小规模生产 + 评测 oracle |
| 元启发式 | ALNS / 迭代局部搜索（自研轻量实现） | 大候选集，呼应 paper-insights 的 ILS |
| 多目标 | NSGA-II 或标量化扫描 | Pareto 前沿 |
| LLM | 现有 OpenAI 兼容（DeepSeek）| 复用 `llm/client.py`，加 function-calling JSON 约束 |
| 缓存 | LRU + SQLite | 幂等 LLM 调用 |
| 状态持久化 | SQLite（已配 `app_state_sqlite_path`）/ Postgres | 复用 `trip_store.py` 模式 |
| 评测/CI | 自研 `eval/` + GitHub Actions | 指标作为 PR gate |

## 附录 B · 与所引论文的对应关系

本方案不是凭空加复杂度，而是把 `skills/local-route-agent/references/paper-insights.md` 里你们自己列出的「完整版设计」落地：

- **OPTW / PersTour（定向越野、时间预算、起止点）** → WP-4。
- **GA / 迭代局部搜索（候选变大时的优化）** → WP-4（ALNS/ILS）。
- **I-AIR / ILSAP（多信号打分、Transformer-GCN，但 MVP 用规则）** → WP-3（保留 `ScoreBreakdown` 契约，插入可训练模型）。
- **「Harness Agent 而非生成式 prompt」** → WP-2（plan-act-observe + 工具白名单 + 确定性保底）。
- **「Validate before explaining / 解释需有据」** → WP-6（解释忠实度自动化）。
- **「为未来真实数据接口设计，保留本地 mock 兜底」** → 全程保留 fallback（WP-7/WP-8 不破坏离线可跑）。

> 一句话：把路标走成路。你们已经把「完整版」写进了研究文档，这份方案就是把它逐项变成可提交的代码与可复现的指标。



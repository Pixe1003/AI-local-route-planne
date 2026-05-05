---
title: "AI 本地路线智能规划 Agent 技术规划方案"
subtitle: "基于用户引导 + Harness Engineering + 多工具 Agent 的新版设计"
author: "ChatGPT"
date: "2026-05-02"
lang: zh-CN
mainfont: "Noto Sans CJK SC"
monofont: "Noto Sans Mono CJK SC"
geometry: "a4paper,margin=2.2cm"
fontsize: 11pt
---

# AI 本地路线智能规划 Agent 技术规划方案

## 0. 文档目标

本文档用于指导 Codex 或开发团队实现一个面向美团黑客松命题「现在就出发：AI 本地路线智能规划」的 Agent 系统。

新版方案在原有「LLM + Harness + POI 工具 + UGC 工具 + 路线优化 + 动态重规划」基础上，新增 **用户需求引导层**。原因是：如果完全依赖 UGC 或 Agent 自行推断用户需求，容易出现用户意图模糊、推荐泛化、路线不符合真实需求的问题。因此，系统启动时应通过轻量化引导，让用户快速补充目的地、活动偏好、美食偏好、同行人群、预算范围、时间等关键信息。

最终目标是实现：

> 用户通过自然语言和快捷标签表达需求，系统构建本次出行画像，结合 POI 数据、UGC 评价语义、上下文信息和多目标路线优化算法，生成可执行、低踩雷、可解释、可动态调整的本地吃喝玩乐路线。

---

## 1. 核心设计判断

### 1.1 不能完全依赖 UGC

UGC 能提供真实评价、场景标签、风险提示和路线经验，但 UGC 本质上反映的是「其他用户怎么评价、怎么消费、怎么游玩」，不等于当前用户的真实需求。

如果只依赖 UGC，系统容易推荐：

- 大众热门但不符合用户预算的地点；
- 评分高但排队长的餐厅；
- 适合游客但不适合本地人的路线；
- 适合年轻人但不适合老人或亲子的路线；
- 评论中热度高但与本次出行目标无关的 POI。

因此，UGC 应作为 **证据层和风险识别层**，而不是唯一决策依据。

### 1.2 不能完全依赖 Agent 猜测

如果用户只说：

```text
帮我规划一下下午去哪玩。
```

Agent 很难准确知道：

- 用户从哪里出发；
- 有多长时间；
- 是否想吃饭；
- 是否有预算；
- 是否带老人或小孩；
- 是否怕排队；
- 是想经典景点还是本地生活；
- 是想轻松休闲还是高强度打卡。

如果 Agent 直接规划，只能使用默认假设，容易导致推荐泛化。

### 1.3 新方案的核心改动

新版流程应改为：

```text
用户进入系统
  ↓
需求引导 Onboarding
  ↓
生成本次出行画像 UserNeedProfile
  ↓
Agent 结构化意图 Intent Parsing
  ↓
上下文获取 Context Collection
  ↓
POI 多路召回 Retrieval
  ↓
UGC 语义分析 UGC Analysis
  ↓
POI 与路线多目标评分 Scoring
  ↓
路线优化 Route Optimization
  ↓
约束校验 Validation
  ↓
解释输出 Explanation
  ↓
动态重规划 Replanning
```

一句话概括：

> 先帮助用户表达需求，再让 Agent 和 UGC 去完成匹配、优化和解释。

---

## 2. 新版系统总体架构

### 2.1 架构总览

```text
Frontend 用户入口
  ↓
Onboarding Agent 需求引导 Agent
  ↓
Orchestrator Agent 总控调度 Agent
  ↓
Intent Agent 意图结构化 Agent
  ↓
Context Agent 上下文感知 Agent
  ↓
POI Retrieval Agent 候选召回 Agent
  ↓
UGC Analysis Agent 评价语义 Agent
  ↓
Preference Agent 用户偏好建模 Agent
  ↓
Scoring Agent 多目标评分 Agent
  ↓
Route Optimization Agent 路线优化 Agent
  ↓
Validation Harness 约束校验器
  ↓
Explanation Agent 解释生成 Agent
  ↓
Replanning Agent 动态重规划 Agent
```

### 2.2 设计原则

系统必须遵循以下原则：

1. **LLM 不直接生成最终路线**：LLM 负责理解、调度、解释；路线由确定性工具和优化算法生成。
2. **用户需求先引导再推断**：关键槽位不足时，优先引导用户补充，而不是让模型猜。
3. **硬约束先过滤，软约束再评分**：营业时间、预算上限、时间预算等硬约束必须优先满足。
4. **POI 好不等于路线好**：路线需要考虑顺序、时间窗、距离、停留时长、排队、预算和体验节奏。
5. **每个推荐必须可解释**：推荐理由应来自用户需求、POI 属性、UGC 标签、评分结果或约束校验。
6. **每条路线必须可调整**：支持少排队、省钱、少走路、雨天、亲子、老人友好等动态修改。
7. **Agent 状态可控**：采用分层状态机 + DAG 工具编排 + 事件驱动重规划，而不是完全自由的 Agent。

---

## 3. 用户需求引导层设计

### 3.1 模块定位

新增模块名称建议：

- `Onboarding Agent`
- `Slot Filling Agent`
- `Travel Intent Onboarding`
- `User Need Profiling Agent`

推荐命名：**Onboarding Agent**。

它的职责是：

1. 判断用户输入是否足够规划路线；
2. 识别缺失槽位；
3. 通过快捷标签或简短问题引导用户补充；
4. 生成本次出行画像 `UserNeedProfile`；
5. 将完整需求交给后续 Agent 工具链。

### 3.2 需要采集的核心槽位

#### 3.2.1 目的地 / 出发地

问题示例：

```text
你现在从哪里出发？想在哪个城市或片区游玩？
```

快捷选项：

```text
[当前位置] [酒店附近] [某个商圈] [某个景点] [手动输入]
```

字段示例：

```json
{
  "city": "南京",
  "start_location": "新街口",
  "target_area": "秦淮区"
}
```

#### 3.2.2 游玩时间

问题示例：

```text
你大概有多长时间？
```

快捷选项：

```text
[2 小时以内] [半天] [一天] [晚上] [自定义]
```

字段示例：

```json
{
  "start_time": "14:00",
  "end_time": "20:00",
  "time_budget_minutes": 360
}
```

#### 3.2.3 景点 / 活动偏好

问题示例：

```text
你更想安排哪些类型的地点？
```

多选标签：

```text
[经典景点] [本地街区] [小众打卡] [博物馆/展览]
[自然公园] [夜景/夜游] [购物商圈] [咖啡休息]
[亲子活动] [情侣约会] [Citywalk]
```

字段示例：

```json
{
  "activity_preferences": ["本地街区", "小众打卡", "咖啡休息", "夜景"]
}
```

#### 3.2.4 美食偏好

问题示例：

```text
你这次想吃什么？
```

多选标签：

```text
[本地特色] [火锅/烧烤] [小吃] [咖啡甜品]
[轻食] [高评分餐厅] [网红店] [性价比]
[不排队] [适合聚餐]
```

口味标签：

```text
[辣] [清淡] [甜口] [重口] [无所谓]
```

字段示例：

```json
{
  "food_preferences": ["本地特色", "性价比", "不排队"],
  "taste_preferences": ["清淡"]
}
```

#### 3.2.5 同行人群

问题示例：

```text
这次和谁一起出行？
```

选项：

```text
[一个人] [情侣] [朋友] [亲子] [带老人]
[同事/商务] [外地游客] [本地居民]
```

不同人群对应策略：

| 人群 | 路线策略 |
|---|---|
| 一个人 | 高自由度、少排队、轻量路线 |
| 情侣 | 拍照、氛围、咖啡、夜景权重提高 |
| 朋友 | 餐饮、娱乐、互动性权重提高 |
| 亲子 | 安全、卫生、亲子友好、休息点权重提高 |
| 带老人 | 少走路、少换乘、座位、无障碍权重提高 |
| 外地游客 | 城市代表性、本地特色、经典点权重提高 |
| 本地居民 | 降低传统景点，提高本地生活、小众店权重 |

#### 3.2.6 预算范围

问题示例：

```text
人均预算大概是多少？
```

选项：

```text
[50 元以内] [50-100 元] [100-200 元] [200-500 元]
[不限制] [自定义]
```

字段示例：

```json
{
  "budget_per_person": 150,
  "budget_strict": false
}
```

### 3.3 可选路线风格

为降低表达成本，入口可以提供风格模板：

```text
[轻松不累] [少排队] [省钱优先] [高评分不踩雷]
[本地人玩法] [经典游客路线] [小众 Citywalk]
[情侣约会] [亲子友好] [雨天室内] [夜游路线]
```

这些标签直接影响权重。

示例：少排队模式

```json
{
  "weights": {
    "queue_penalty": 0.35,
    "distance_penalty": 0.15,
    "rating_score": 0.20,
    "interest_score": 0.20,
    "price_score": 0.10
  }
}
```

示例：带老人模式

```json
{
  "weights": {
    "walking_penalty": 0.35,
    "transfer_penalty": 0.20,
    "rest_stop_score": 0.20,
    "crowd_penalty": 0.15,
    "classic_spot_score": 0.10
  }
}
```

### 3.4 需求完整度评分

Onboarding Agent 应计算 `intent_completeness_score`。

```json
{
  "intent_completeness_score": 0.72,
  "missing_slots": ["budget_per_person", "party_type"],
  "can_plan": true,
  "should_ask_followup": true
}
```

建议规则：

| 完整度 | 处理方式 |
|---|---|
| 0.8 以上 | 直接规划 |
| 0.5-0.8 | 可先规划，同时提示用户补充 |
| 0.5 以下 | 先引导用户补充关键信息 |

必填槽位建议：

- 出发地或当前位置；
- 游玩时间或大致时长；
- 至少一个活动或美食偏好；
- 同行人群；
- 预算范围。

---

## 4. 核心数据结构

### 4.1 UserNeedProfile

```json
{
  "destination": {
    "city": "南京",
    "start_location": "新街口",
    "target_area": "秦淮区",
    "end_location": "酒店"
  },
  "time": {
    "start_time": "14:00",
    "end_time": "20:00",
    "time_budget_minutes": 360
  },
  "activity_preferences": ["本地街区", "拍照", "夜景"],
  "food_preferences": ["南京本地菜", "性价比", "少排队"],
  "taste_preferences": ["清淡"],
  "party_type": "朋友",
  "budget": {
    "budget_per_person": 150,
    "strict": false
  },
  "route_style": ["轻松", "少排队"],
  "avoid": ["长距离步行", "长时间排队"],
  "must_visit": [],
  "must_avoid": [],
  "completeness_score": 0.86
}
```

### 4.2 AgentRunState

```json
{
  "run_id": "run_001",
  "session_id": "session_001",
  "phase": "PLANNING",
  "user_need_profile": {},
  "user_intent": {},
  "context": {},
  "candidate_pois": [],
  "ugc_summaries": {},
  "scored_pois": [],
  "candidate_routes": [],
  "selected_route": null,
  "validation_result": null,
  "events": [],
  "replan_level": null,
  "iteration_count": 0,
  "errors": [],
  "warnings": [],
  "trace": []
}
```

### 4.3 POI

```json
{
  "poi_id": "poi_001",
  "name": "南京本地菜馆A",
  "category": "food",
  "sub_category": "南京菜",
  "lat": 32.0,
  "lng": 118.7,
  "rating": 4.7,
  "review_count": 3280,
  "avg_price": 118,
  "queue_time": 12,
  "open_hours": [],
  "tags": ["本地菜", "有团购", "适合朋友"],
  "has_deal": true
}
```

### 4.4 ScoredPOI

```json
{
  "poi_id": "poi_001",
  "total_score": 86.5,
  "score_breakdown": {
    "user_interest": 24.0,
    "poi_quality": 22.0,
    "context_fit": 15.0,
    "ugc_match": 18.0,
    "service_closure": 10.0,
    "queue_penalty": -2.5
  },
  "risks": ["周末高峰可能排队"],
  "recommendation_reason": "匹配南京本地菜和低排队需求"
}
```

### 4.5 RoutePlan

```json
{
  "route_id": "route_001",
  "title": "轻松本地体验路线",
  "stops": [
    {
      "poi_id": "poi_001",
      "name": "老门东街区",
      "arrival_time": "14:20",
      "departure_time": "15:30",
      "stay_minutes": 70,
      "travel_from_previous_minutes": 20,
      "estimated_cost": 0,
      "reason": "适合拍照和街区漫游"
    }
  ],
  "total_time_minutes": 350,
  "total_cost": 138,
  "total_walking_distance": 2.8,
  "total_queue_time": 24,
  "route_score": 91.2,
  "warnings": [],
  "alternatives": []
}
```

---

## 5. 新版 Agent 状态机设计

### 5.1 顶层状态机

新版状态机不应是完全线性的，而应采用 **分层状态机 + DAG 工具编排 + 事件驱动重规划**。

顶层状态：

```text
IDLE
  ↓
ONBOARDING
  ↓
UNDERSTANDING
  ↓
PLANNING
  ↓
VALIDATING
  ↓
PRESENTING
  ↓
WAITING_FOR_FEEDBACK
  ↓
REPLANNING / COMPLETED
```

### 5.2 状态含义

| 状态 | 含义 |
|---|---|
| IDLE | 等待用户输入 |
| ONBOARDING | 引导用户补充需求槽位 |
| UNDERSTANDING | 将需求画像转成结构化意图 |
| PLANNING | 召回、分析、评分、规划路线 |
| VALIDATING | 校验时间、预算、营业时间、排队等约束 |
| REPAIRING | 校验失败时自动修复 |
| PRESENTING | 展示路线和解释 |
| WAITING_FOR_FEEDBACK | 等待用户修改、确认或追问 |
| REPLANNING | 动态重规划 |
| COMPLETED | 当前任务结束 |
| FAILED | 找不到可行路线或系统异常 |

### 5.3 状态转移表

```python
TRANSITIONS = {
    "IDLE": ["ONBOARDING"],
    "ONBOARDING": ["UNDERSTANDING", "NEED_MORE_INFO"],
    "NEED_MORE_INFO": ["ONBOARDING"],
    "UNDERSTANDING": ["PLANNING"],
    "PLANNING": ["VALIDATING"],
    "VALIDATING": ["PRESENTING", "REPAIRING", "FAILED"],
    "REPAIRING": ["VALIDATING", "FAILED"],
    "PRESENTING": ["WAITING_FOR_FEEDBACK"],
    "WAITING_FOR_FEEDBACK": ["REPLANNING", "COMPLETED"],
    "REPLANNING": ["VALIDATING"],
    "FAILED": ["IDLE"],
    "COMPLETED": ["IDLE"]
}
```

---

## 6. PLANNING 阶段的 DAG 工具编排

PLANNING 阶段内部可以采用 DAG，而不是简单串行。

```text
user_need_profile
        ↓
normalize_constraints
        ↓
 ┌─────────────┬─────────────┬──────────────┐
 ↓             ↓             ↓              ↓
geo_retrieve   semantic_retrieve  category_retrieve  popular_retrieve
 ↓             ↓             ↓              ↓
 └─────────────┴────── merge_candidates ────┘
                        ↓
                enrich_with_ugc
                        ↓
                score_candidates
                        ↓
                optimize_route
                        ↓
                validate_route
                        ↓
                explain_route
```

好处：

- 多路召回可以并行；
- 单一路径失败不影响整体；
- 可缓存中间结果；
- 可插拔扩展；
- 可观测性强。

---

## 7. 动态重规划设计

### 7.1 事件类型

```text
USER_MODIFY_CONSTRAINT
USER_REJECT_POI
USER_ASK_WHY
USER_CONFIRM_ROUTE
QUEUE_TIME_CHANGED
WEATHER_CHANGED
POI_CLOSED
TIME_DELAYED
USER_LOCATION_DEVIATED
BUDGET_EXCEEDED
ROUTE_VALIDATION_FAILED
```

### 7.2 重规划等级

| 等级 | 场景 | 处理方式 |
|---|---|---|
| Level 1 Minor | 换一家餐厅、少排队 | 只替换一个 POI |
| Level 2 Partial | 下雨、用户延误、后续时间不足 | 保留已完成部分，重排剩余路线 |
| Level 3 Full | 目标变了、只剩 2 小时、换区域 | 重新进入 Onboarding 或 Understanding |

### 7.3 示例

用户说：

```text
这家店排队太久了，换一家。
```

系统判断：

```json
{
  "event_type": "USER_REJECT_POI",
  "replan_level": "minor",
  "strategy": "replace_single_poi",
  "target_category": "food"
}
```

用户说：

```text
下雨了，后面别安排户外。
```

系统判断：

```json
{
  "event_type": "WEATHER_CHANGED",
  "replan_level": "partial",
  "strategy": "replan_remaining_route",
  "new_constraints": {
    "indoor_only": true
  }
}
```

---

## 8. 多目标评分模型

### 8.1 POI 评分

```text
poi_score =
  α * user_interest_score
+ β * poi_quality_score
+ γ * context_fit_score
+ δ * ugc_match_score
+ ε * service_closure_score
- λ1 * queue_penalty
- λ2 * price_penalty
- λ3 * distance_penalty
- λ4 * risk_penalty
```

解释：

| 指标 | 含义 |
|---|---|
| user_interest_score | 是否符合用户活动、美食、同行人群偏好 |
| poi_quality_score | 评分、评论数、热度、服务质量 |
| context_fit_score | 时间、天气、位置、营业状态适配 |
| ugc_match_score | 评论语义是否匹配用户需求 |
| service_closure_score | 是否可团购、订票、预约、排队、导航 |
| queue_penalty | 排队过长惩罚 |
| price_penalty | 超预算惩罚 |
| distance_penalty | 距离过远惩罚 |
| risk_penalty | 差评、拥挤、闭店等风险惩罚 |

### 8.2 路线评分

```text
route_score =
  Σ poi_score
+ route_coherence_score
+ time_rhythm_score
+ category_coverage_score
+ consumption_closure_score
- travel_time_penalty
- walking_penalty
- waiting_penalty
- budget_penalty
- detour_penalty
- fatigue_penalty
- risk_penalty
```

### 8.3 路线节奏规则

| 时间段 | 推荐类型 |
|---|---|
| 早上 | 早餐、博物馆、公园、文化景点 |
| 中午 | 正餐、商圈休息 |
| 下午 | 街区、咖啡、展馆、轻体验 |
| 傍晚 | 晚餐、拍照、江边、老城街区 |
| 晚上 | 夜景、夜市、酒吧、演出 |

---

## 9. 约束校验与修复

### 9.1 必须校验的硬约束

- POI 是否真实存在；
- 到达时是否营业；
- 总时间是否超过预算；
- 总消费是否超过硬预算；
- 是否包含用户必选类别；
- 是否包含用户必去点；
- 路线是否可达；
- 是否存在明显绕路；
- 排队是否超过硬阈值。

### 9.2 校验失败后的修复策略

| 失败原因 | 修复策略 |
|---|---|
| 未营业 | 替换同类营业 POI |
| 超预算 | 替换低价或团购 POI |
| 超时 | 删除低优先级 POI 或压缩停留时间 |
| 排队过长 | 替换低排队 POI |
| 缺少必选类别 | 插入该类别最高分 POI |
| 距离过远 | 替换同区域 POI |
| 下雨户外过多 | 替换室内 POI |

最多修复 2 次，避免无限循环。

---

## 10. API 设计

### 10.1 POST /api/onboarding/analyze

作用：分析用户输入完整度，返回缺失槽位和引导问题。

输入：

```json
{
  "query": "下午想在南京轻松逛逛，吃点本地菜"
}
```

输出：

```json
{
  "completeness_score": 0.58,
  "missing_slots": ["start_location", "time_budget", "party_type", "budget"],
  "suggested_questions": [
    "你从哪里出发？",
    "你大概有多长时间？",
    "和谁一起出行？",
    "人均预算大概是多少？"
  ],
  "can_plan": true
}
```

### 10.2 POST /api/onboarding/profile

作用：根据用户回答生成 `UserNeedProfile`。

### 10.3 POST /api/plan-route

作用：根据用户画像生成路线。

### 10.4 POST /api/replan-route

作用：根据用户反馈或实时事件重规划。

### 10.5 POST /api/explain-route

作用：生成路线解释。

---

## 11. 前端交互设计

### 11.1 首页入口

标题：

```text
今天想怎么玩？
```

输入框 placeholder：

```text
例如：下午想在南京轻松逛逛，吃点本地菜，不想排队。
```

快捷标签：

```text
[半天] [夜游] [情侣] [亲子] [带老人]
[少排队] [本地美食] [小众拍照] [雨天室内]
```

### 11.2 引导问题卡片

如果信息不完整，展示：

```text
为了帮你规划得更准，请补充 3 个信息：
1. 你从哪里出发？
2. 你大概有多长时间？
3. 人均预算是多少？
```

### 11.3 出行需求确认卡

规划前展示：

```text
本次路线需求：
- 出发地：新街口
- 时间：14:00-20:00
- 风格：轻松、少排队、本地特色
- 美食：南京本地菜
- 同行：朋友
- 预算：人均 150 元
```

用户可点击修改。

### 11.4 路线展示

路线展示应包含：

- 时间轴；
- POI 卡片；
- 推荐理由；
- 风险提示；
- 总耗时；
- 总预算；
- 总步行距离；
- 排队风险；
- 动态调整按钮。

动态按钮：

```text
[少排队] [更省钱] [少走路] [雨天方案]
[亲子友好] [老人友好] [压缩到 2 小时]
```

---

## 12. 后端目录结构建议

```text
ai-local-route-agent/
  backend/
    app/
      main.py
      api/
        routes.py
      schemas/
        onboarding.py
        intent.py
        poi.py
        route.py
        context.py
        validation.py
      harness/
        orchestrator.py
        state_machine.py
        tool_registry.py
        memory.py
        logger.py
      tools/
        onboarding_agent.py
        intent_parser.py
        context_provider.py
        poi_retriever.py
        ugc_analyzer.py
        preference_builder.py
        poi_scorer.py
        route_optimizer.py
        route_validator.py
        route_replanner.py
        explanation_generator.py
      data/
        pois.json
        reviews.json
        poi_edges.json
      tests/
        test_onboarding_agent.py
        test_intent_parser.py
        test_poi_retriever.py
        test_poi_scorer.py
        test_route_optimizer.py
        test_route_validator.py
        test_replanner.py
        test_orchestrator.py
  frontend/
    app/
      page.tsx
    components/
      OnboardingPanel.tsx
      NeedProfileCard.tsx
      RouteTimeline.tsx
      RouteSummary.tsx
      PoiCard.tsx
      ReplanButtons.tsx
      ExplanationPanel.tsx
  README.md
```

---

## 13. MVP 开发阶段

### Phase 1：需求引导与用户画像

目标：

- 实现 Onboarding Agent；
- 实现槽位识别；
- 实现完整度评分；
- 实现用户出行画像结构；
- 前端实现引导卡片。

交付：

- `/api/onboarding/analyze`
- `/api/onboarding/profile`
- `UserNeedProfile`
- `OnboardingPanel`
- `NeedProfileCard`

### Phase 2：POI 召回与 UGC 标签

目标：

- 使用本地 JSON 模拟 POI；
- 使用本地 JSON 模拟评论标签；
- 实现多路召回；
- 实现 UGC 标签匹配。

交付：

- `poi_retriever.py`
- `ugc_analyzer.py`
- `pois.json`
- `reviews.json`

### Phase 3：评分与路线生成

目标：

- 实现 POI 多目标评分；
- 实现路线评分；
- 实现 Beam Search / Greedy 初版路线生成；
- 实现时间、预算、营业时间校验。

交付：

- `poi_scorer.py`
- `route_optimizer.py`
- `route_validator.py`
- `/api/plan-route`

### Phase 4：动态重规划与解释

目标：

- 实现少排队、省钱、少走路、雨天重规划；
- 实现推荐理由生成；
- 前端实现动态按钮。

交付：

- `route_replanner.py`
- `explanation_generator.py`
- `/api/replan-route`
- `ReplanButtons`
- `ExplanationPanel`

### Phase 5：黑客松 Demo 优化

目标：

- 准备 3 个演示场景；
- 优化响应速度；
- 优化 UI 展示；
- 增加方案对比。

演示场景：

1. 外地游客半日游；
2. 情侣夜游 + 本地菜；
3. 亲子雨天室内路线。

---

## 14. 测试要求

### 14.1 Onboarding 测试

- 用户未提供时间时，应识别 `time_budget` 缺失；
- 用户未提供预算时，应识别 `budget` 缺失；
- 用户说“带老人”时，应生成低步行约束；
- 用户说“不想排队”时，应提高排队惩罚权重；
- 完整度低于 0.5 时，应返回追问问题。

### 14.2 规划测试

- 不允许安排未营业 POI；
- 不允许超过硬预算；
- 不允许超过时间预算；
- 必须包含用户要求的类别；
- 每个 POI 必须来自数据源；
- 推荐理由必须来自 POI 属性、UGC 标签或评分结果。

### 14.3 重规划测试

- “少排队”后，总排队时间应下降；
- “更省钱”后，总预算应下降；
- “下雨了”后，户外 POI 数量应减少；
- “只剩 2 小时”后，总路线时长应压缩；
- 替换 POI 后，路线仍应通过约束校验。

---

## 15. Codex 开发提示词

```text
请基于当前方案开发一个 AI 本地路线智能规划 Agent 的新版 MVP。

核心变化：
在原有路线规划 Agent 前增加 Onboarding Agent，
用于在系统启动时引导用户补充需求。
不要完全依赖 UGC 或 LLM 猜测用户需求。

技术栈：
- 后端：FastAPI + Python + Pydantic
- 前端：Next.js + TypeScript
- 数据：先使用本地 JSON
- 暂不接真实美团接口
- 暂不接真实 LLM API，可用 mock LLM 或规则函数

架构要求：
1. 采用 Harness Engineering 思路。
2. LLM 不直接生成路线，只负责意图解析和解释。
3. 路线由 POI 召回、评分、优化和校验模块生成。
4. 采用分层状态机 + DAG 工具编排 + 事件驱动重规划。
5. 所有状态转移必须显式定义。
6. 所有推荐理由必须有数据来源。

新增模块：
- tools/onboarding_agent.py
- schemas/onboarding.py
- components/OnboardingPanel.tsx
- components/NeedProfileCard.tsx

后端模块：
- harness/orchestrator.py
- harness/state_machine.py
- harness/tool_registry.py
- tools/intent_parser.py
- tools/context_provider.py
- tools/poi_retriever.py
- tools/ugc_analyzer.py
- tools/preference_builder.py
- tools/poi_scorer.py
- tools/route_optimizer.py
- tools/route_validator.py
- tools/route_replanner.py
- tools/explanation_generator.py

API：
- POST /api/onboarding/analyze
- POST /api/onboarding/profile
- POST /api/plan-route
- POST /api/replan-route
- POST /api/explain-route

必须实现：
1. 用户输入自然语言后，分析需求完整度。
2. 如果缺少目的地、时间、预算、同行人、偏好等关键槽位，
   返回引导问题。
3. 用户补充后生成 UserNeedProfile。
4. 根据 UserNeedProfile 召回 POI。
5. 根据 POI 属性、UGC 标签、上下文和用户偏好评分。
6. 生成路线并校验约束。
7. 输出推荐理由和风险提示。
8. 支持少排队、省钱、少走路、雨天等动态调整。

测试要求：
- 为以下模块编写 pytest：
  onboarding_agent、intent_parser、poi_retriever、poi_scorer、
  route_optimizer、route_validator、route_replanner、orchestrator。
- 测试必须覆盖：
  缺失槽位识别、完整度评分、路线约束校验、动态重规划。
```

---

## 16. 答辩表述建议

可以这样介绍新版方案：

```text
我们发现，完全依赖 UGC 或大模型推断用户需求是不稳定的，因为用户在启动阶段往往并不清楚或没有完整表达自己的需求。因此，我们在 Agent 前增加了轻量化需求引导层，通过目的地、时间、活动偏好、美食偏好、同行人群和预算范围等关键槽位，快速构建用户本次出行画像。

之后，系统再结合美团 POI 数据、UGC 评价语义、用户偏好、排队、价格、营业时间和空间距离，通过多目标评分和路线优化生成可执行路线。这样既减少了冷启动误判，也增强了用户控制感和路线匹配度。

技术上，我们采用 Harness Engineering 思路，让 LLM 负责意图理解和解释，让确定性工具负责召回、评分、优化、校验和动态重规划，避免大模型直接生成路线带来的幻觉和不可执行问题。
```

---

## 17. 最终方案一句话

> 新版方案是在 Agent 路线规划前增加用户需求引导层，通过轻量化槽位补全构建本次出行画像，再结合 POI 数据、UGC 语义、多目标评分、路线优化和动态重规划，生成可执行、可解释、低踩雷、可消费闭环的本地生活路线。

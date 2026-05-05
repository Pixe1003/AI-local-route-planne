# AI 本地路线智能规划 Agent 技术规划总结要求

> 适用场景：美团黑客松命题「现在就出发：AI 本地路线智能规划」
> 交付对象：Codex / 开发协作窗口 / 项目团队
> 文档目标：把前述论文经验转化为可开发、可测试、可演示的 Agent 技术方案。

---

## 0. 一句话结论

本项目的 Agent 不应设计成一个「大模型直接生成路线」的聊天机器人，而应设计成一个 **LLM + Harness + Tools + Validator + Replanner** 的工程化 Agent 系统。

核心架构建议为：

```text
分层状态机
+ DAG 工具编排
+ 事件驱动重规划
+ 校验失败修复循环
+ 黑板式共享状态
```

最终目标是生成一条 **可执行、低踩雷、可消费闭环、可动态调整** 的本地吃喝玩乐路线。

---

## 1. 项目定位

### 1.1 用户问题

用户并不只是想知道「附近有什么好玩的」，而是想解决一个完整决策问题：

```text
我现在在哪里？
我有多少时间？
我预算多少？
我想吃什么、玩什么？
我是否怕排队、怕累、怕踩雷？
哪些地点现在营业？
怎么走最顺？
中途情况变化后怎么调整？
```

因此，系统不能只输出 POI 列表，而要输出完整路线。

### 1.2 产品目标

系统应能完成：

1. 理解用户自然语言需求。
2. 将需求转化为结构化路线约束。
3. 召回真实或模拟 POI 候选。
4. 分析 UGC 评论中的体验标签和风险标签。
5. 对 POI 和路线进行多目标评分。
6. 生成满足时间、预算、营业、排队、距离等约束的路线。
7. 校验路线是否真实可执行。
8. 解释推荐理由。
9. 支持动态调整：少排队、省钱、少走路、雨天、亲子、老人友好、压缩路线等。

### 1.3 产品边界

MVP 阶段不做：

- 不接真实美团接口。
- 不做真实交易、支付、下单。
- 不训练深度学习模型。
- 不做完整 GCN / Transformer 推荐模型。
- 不做复杂实时交通系统。

MVP 阶段要做：

- 本地 JSON 模拟 POI 数据。
- 本地 JSON 模拟 UGC 标签。
- 规则型意图解析。
- 多目标评分。
- Beam Search / 贪心 + Local Search 路线生成。
- 显式约束校验。
- 动态重规划。
- 前端 Demo 展示。

---

## 2. 论文经验到工程设计的映射

| 论文方向 | 可借鉴经验 | 工程转化 |
|---|---|---|
| SCATEAgent | 上下文感知、动态调整、多 Agent 协作 | Context Agent、Replanning Agent、实时事件监听 |
| PersTour | 用户兴趣、POI 停留时长、时间预算 | 个性化停留时间、兴趣向量、时间约束路线 |
| ILSAP | 用户兴趣预测、POI 特征、局部搜索、自适应扰动 | POI 多目标评分、Local Search、分级重规划 |
| I-AIR | 多信号融合、POI 共访图、意图感知路线 | 多路召回、POI 边关系、用户意图建模 |
| OD 目的地预测 | 候选目的地补充、冷启动处理 | 多路候选 POI 召回、群体热门、空间邻近 |
| UGC 路线挖掘 | 从评论/游记中抽取路线经验和区域结构 | UGC 标签抽取、片区路线表达、风险提示 |
| GA 路线推荐 | 大规模候选组合下的启发式优化 | Beam Search / GA / Local Search 可选优化器 |
| Color-Coding 路径搜索 | 必去点、类别、距离上限下的路径约束 | 硬约束校验、类别覆盖、最大距离/时间限制 |
| AI chatbot 预订研究 | 用户控制感、解释、可修改性 | 解释 Agent、替代方案、重规划按钮 |
| AI 网站质量研究 | 移动端性能、AI 页面响应速度 | 首屏快响应、异步解释、缓存、后端计算 |
| 智慧目的地研究 | AI 需嵌入本地服务生态 | 接入 POI、评价、排队、团购、营业状态、商圈关系 |

---

## 3. Agent 总体设计原则

### 3.1 不做纯 Prompt Agent

错误架构：

```text
用户输入 → Prompt → LLM 直接生成路线
```

风险：

- 编造 POI。
- 编造营业时间。
- 编造价格和团购。
- 忽略硬约束。
- 难以复现。
- 难以测试。
- 难以动态调整。

### 3.2 做 Harness Agent

推荐架构：

```text
用户输入
  ↓
LLM Orchestrator
  ↓
Harness 工具层
  ├── Intent Parser
  ├── Context Manager
  ├── POI Retriever
  ├── UGC Analyzer
  ├── POI Scorer
  ├── Route Optimizer
  ├── Constraint Validator
  ├── Route Replanner
  └── Explanation Generator
```

其中：

- LLM 负责理解、调度、解释。
- Harness 负责流程、状态、工具调用、校验、重试、回滚。
- 工具负责确定性计算。
- Validator 负责防幻觉和硬约束。
- Replanner 负责动态调整。

### 3.3 核心原则

1. **先结构化，再生成。**
   LLM 先输出 JSON，不直接输出路线。

2. **先过滤硬约束，再排序。**
   不营业、不可达、超预算、无真实数据的 POI 不进入路线。

3. **POI 好不等于路线好。**
   路线还要考虑顺序、节奏、距离、预算、排队和体力。

4. **每条路线必须可验证。**
   输出前必须经过 Constraint Validator。

5. **每个推荐必须有证据。**
   推荐理由必须来自 POI 属性、UGC 标签、评分结果或路线约束。

6. **每条路线必须可调整。**
   用户可以切换少排队、省钱、少走路、雨天方案等。

---

## 4. Agent 架构选择

### 4.1 线性状态机是否最优

线性状态机不是最终最优，但适合 MVP。

基础线性流程：

```text
PARSE → RETRIEVE → SCORE → PLAN → VALIDATE → EXPLAIN
```

优点：

- 简单。
- 稳定。
- 易测试。
- 适合黑客松快速开发。

缺点：

- 不适合用户中途修改。
- 不适合实时事件触发。
- 不适合并行召回。
- 不适合失败修复。
- 不适合多方案动态比较。

### 4.2 推荐最终架构

采用：

```text
分层状态机 + DAG 工具编排 + 事件驱动重规划 + 校验修复循环 + 黑板式共享状态
```

这是一种可控非线性架构。

含义：

- 顶层状态机保证流程可控。
- PLANNING 内部用 DAG 编排工具。
- 实时变化由事件触发。
- 校验失败进入修复循环。
- 所有模块围绕共享状态读写。

---

## 5. 顶层状态机设计

### 5.1 顶层状态

```text
IDLE
  ↓
UNDERSTANDING
  ↓
NEED_CLARIFICATION / PLANNING
  ↓
VALIDATING
  ↓
REPAIRING / PRESENTING / FAILED
  ↓
WAITING_FOR_FEEDBACK
  ↓
REPLANNING / COMPLETED
```

### 5.2 状态说明

| 状态 | 说明 |
|---|---|
| IDLE | 等待用户输入 |
| UNDERSTANDING | 解析用户意图 |
| NEED_CLARIFICATION | 用户信息不足，需要追问 |
| PLANNING | 召回、评分、路线生成 |
| VALIDATING | 校验路线硬约束 |
| REPAIRING | 自动修复失败路线 |
| PRESENTING | 展示路线和解释 |
| WAITING_FOR_FEEDBACK | 等待用户确认、修改或追问 |
| REPLANNING | 根据用户反馈或实时事件重规划 |
| FAILED | 无可行路线或系统失败 |
| COMPLETED | 当前任务完成 |

### 5.3 显式状态转移表

```python
TRANSITIONS = {
    "IDLE": ["UNDERSTANDING"],
    "UNDERSTANDING": ["NEED_CLARIFICATION", "PLANNING"],
    "NEED_CLARIFICATION": ["UNDERSTANDING"],
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

## 6. PLANNING 阶段 DAG 工具编排

### 6.1 工具编排流程

```text
parse_intent
     ↓
get_context
     ↓
┌───────────────────┬────────────────────┬────────────────────┐
│ semantic_retrieve │ geo_retrieve        │ popularity_retrieve │
└───────────────────┴────────────────────┴────────────────────┘
     ↓
merge_candidates
     ↓
analyze_ugc
     ↓
score_pois
     ↓
optimize_route
     ↓
validate_route
     ↓
explain_route
```

### 6.2 为什么使用 DAG

DAG 工具编排的好处：

- 多路召回可以并行。
- 某一路召回失败不影响整体。
- 可以缓存中间结果。
- 可以观测每个工具耗时。
- 可以单独测试每个节点。

MVP 阶段可以先用同步调用实现，代码结构上保留 DAG 思路。

---

## 7. 事件驱动重规划设计

### 7.1 事件类型

```text
USER_NEW_REQUEST
USER_MODIFY_CONSTRAINT
USER_ASK_WHY
USER_REJECT_POI
USER_CONFIRM_ROUTE
QUEUE_TIME_CHANGED
WEATHER_CHANGED
POI_CLOSED
TIME_DELAYED
USER_LOCATION_DEVIATED
BUDGET_EXCEEDED
ROUTE_VALIDATION_FAILED
```

### 7.2 事件到重规划等级

| 事件 | 重规划等级 | 策略 |
|---|---|---|
| 用户说“换一家餐厅” | Level 1 | 单点替换 |
| 排队时间变长 | Level 1 | 替换目标 POI |
| 下雨 | Level 2 | 保留已完成部分，重排剩余路线 |
| 用户走慢导致时间不足 | Level 2 | 删除低优先级点并重排 |
| 只剩 2 小时 | Level 3 | 全局重规划 |
| 用户完全换目标 | Level 3 | 重新解析意图并规划 |

### 7.3 重规划等级

```text
Level 1：Minor Replan
只替换一个 POI，不改变整体路线结构。

Level 2：Partial Replan
保留已完成部分，重排剩余路线。

Level 3：Full Replan
重新解析用户意图，生成完整新路线。
```

---

## 8. 黑板式共享状态设计

### 8.1 AgentRunState

所有工具围绕同一个 AgentRunState 读写。

```json
{
  "run_id": "run_001",
  "session_id": "session_001",
  "phase": "PLANNING",
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
  "repair_attempts": 0,
  "errors": [],
  "warnings": [],
  "trace": []
}
```

### 8.2 设计要求

- 每个工具只修改自己负责的字段。
- 所有状态变更写入 trace。
- 所有错误写入 errors。
- 所有风险写入 warnings。
- 每次重规划保留历史版本，支持回滚。

---

## 9. 核心工具设计要求

### 9.1 parse_intent

职责：把自然语言转成结构化约束。

```python
def parse_intent(user_query: str, user_context: dict) -> UserIntent:
    ...
```

必须识别：

- 起点。
- 终点。
- 出发时间。
- 结束时间。
- 时间预算。
- 人均预算。
- 同行人。
- 偏好。
- 避免项。
- 必选类别。
- 硬约束。
- 软约束。

### 9.2 get_context

职责：获取当前上下文。

```python
def get_context(location: str, time: str) -> Context:
    ...
```

上下文包括：

- 当前时间。
- 当前地点。
- 天气。
- 交通。
- 营业状态。
- 排队状态。
- 已完成站点。
- 剩余时间。

### 9.3 retrieve_pois

职责：多路召回候选 POI。

```python
def retrieve_pois(intent: UserIntent, context: Context) -> list[POI]:
    ...
```

召回方式：

- 语义召回。
- 地理召回。
- 类别召回。
- 热门召回。
- 个性化召回。
- UGC 标签召回。
- 共访图召回。
- 时间召回。
- 天气召回。
- 备用召回。

### 9.4 analyze_ugc

职责：把评论转成结构化标签。

```python
def analyze_ugc(poi_ids: list[str]) -> dict[str, UGCSummary]:
    ...
```

输出：

- 正向标签。
- 负向标签。
- 人群标签。
- 时间标签。
- 天气标签。
- 风险标签。
- 评论摘要。

### 9.5 score_pois

职责：给 POI 打分。

```python
def score_pois(
    pois: list[POI],
    intent: UserIntent,
    context: Context,
    ugc: dict[str, UGCSummary]
) -> list[ScoredPOI]:
    ...
```

评分公式：

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

### 9.6 optimize_route

职责：生成候选路线并选择最优路线。

```python
def optimize_route(
    scored_pois: list[ScoredPOI],
    intent: UserIntent,
    context: Context
) -> RoutePlan:
    ...
```

MVP 算法：

```text
Route Skeleton + Beam Search + Local Search
```

### 9.7 validate_route

职责：校验路线是否可执行。

```python
def validate_route(route: RoutePlan, intent: UserIntent, context: Context) -> ValidationResult:
    ...
```

必须校验：

- POI 是否存在。
- POI 是否营业。
- 总时间是否超预算。
- 总费用是否超预算。
- 必选类别是否覆盖。
- 必去点是否包含。
- 排队是否超阈值。
- 步行距离是否过高。

### 9.8 repair_route

职责：校验失败后自动修复。

```python
def repair_route(route: RoutePlan, validation: ValidationResult, state: AgentRunState) -> RoutePlan:
    ...
```

修复策略：

- 替换未营业 POI。
- 替换超预算 POI。
- 替换排队过长 POI。
- 删除低分 POI。
- 交换访问顺序。
- 压缩停留时间。

最大修复次数：2 次。

### 9.9 replan_route

职责：根据用户反馈或实时事件重规划。

```python
def replan_route(
    current_route: RoutePlan,
    event: AgentEvent,
    state: AgentRunState
) -> RoutePlan:
    ...
```

### 9.10 explain_route

职责：生成解释。

```python
def explain_route(route: RoutePlan, intent: UserIntent, validation: ValidationResult) -> str:
    ...
```

解释必须基于：

- 用户偏好。
- POI 属性。
- UGC 标签。
- 评分结果。
- 路线约束。
- 校验结果。

不得编造原因。

---

## 10. 数据模型要求

### 10.1 UserIntent

```json
{
  "start_location": "新街口",
  "end_location": "酒店",
  "start_time": "14:00",
  "end_time": "20:00",
  "time_budget_minutes": 360,
  "budget_per_person": 150,
  "party_type": "friends",
  "preferences": ["南京本地菜", "拍照", "咖啡"],
  "avoid": ["长时间排队", "太累"],
  "required_categories": ["food", "photo_spot", "coffee"],
  "hard_constraints": {},
  "soft_constraints": {}
}
```

### 10.2 POI

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

### 10.3 UGCSummary

```json
{
  "poi_id": "poi_001",
  "positive_tags": ["本地特色", "出片", "性价比高"],
  "negative_tags": ["周末排队"],
  "scene_tags": ["情侣", "朋友", "外地游客"],
  "time_tags": ["晚餐"],
  "weather_tags": ["雨天可去"],
  "risk_tags": ["高峰拥挤"],
  "summary": "适合想体验南京本地菜的游客，但周末晚餐排队风险较高。"
}
```

### 10.4 ScoredPOI

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

### 10.5 RoutePlan

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

## 11. API 设计要求

### 11.1 POST /api/plan-route

功能：首次生成路线。

输入：

```json
{
  "query": "我下午2点从新街口出发，晚上8点前回酒店，想吃南京本地菜，不想排太久，人均150以内。",
  "user_context": {
    "current_location": "新街口"
  }
}
```

输出：

```json
{
  "route": {},
  "alternatives": [],
  "explanation": "",
  "validation": {}
}
```

### 11.2 POST /api/replan-route

功能：动态调整路线。

输入：

```json
{
  "route_id": "route_001",
  "change_request": "我不想排队了，帮我换一家晚餐店",
  "current_location": "老门东"
}
```

### 11.3 POST /api/explain-route

功能：解释路线。

输入：

```json
{
  "route_id": "route_001",
  "question": "为什么推荐这家餐厅？"
}
```

---

## 12. 前端展示要求

### 12.1 必须展示

- 自然语言输入框。
- 路线总览卡。
- 时间轴。
- 每站 POI 卡片。
- 推荐理由。
- 风险提示。
- 动态调整按钮。
- 替代方案。

### 12.2 路线总览卡

```text
推荐路线：轻松本地体验路线
总耗时：6 小时
预计消费：人均 138 元
总步行：2.8 公里
排队风险：低
路线风格：本地菜 / 拍照 / 咖啡 / 夜景
```

### 12.3 动态调整按钮

建议按钮：

- 少排队。
- 更省钱。
- 少走路。
- 更小众。
- 更适合拍照。
- 雨天方案。
- 亲子方案。
- 老人友好。
- 压缩到 2 小时。
- 增加一个咖啡休息点。

---

## 13. 非功能要求

### 13.1 性能要求

MVP：

- 首次路线生成不超过 5 秒。
- 动态调整不超过 3 秒。
- 前端首屏不阻塞。
- 推荐理由可异步生成。

后续目标：

- 常见路线缓存。
- 多路召回并行。
- UGC 摘要预计算。

### 13.2 可观测性要求

每次 Agent Run 必须记录：

- 用户输入。
- 解析出的 UserIntent。
- 调用过的工具。
- 每个工具耗时。
- 候选 POI 数量。
- 被过滤 POI 数量。
- 最终路线分数。
- 校验结果。
- 重规划历史。
- 错误和警告。

### 13.3 安全边界

禁止：

- 编造 POI。
- 编造价格。
- 编造团购。
- 编造排队时间。
- 编造营业状态。
- 安排未营业 POI。
- 忽略硬预算。
- 未经用户确认进行下单或支付。

---

## 14. 测试要求

### 14.1 意图解析测试

| 输入 | 期望 |
|---|---|
| 不想太累 | low_walking = true |
| 人均 150 | budget_per_person = 150 |
| 带老人 | elderly_friendly 权重提高 |
| 下雨了 | indoor_only 或 indoor_preferred |
| 不想排队 | max_queue_time 或 low_queue = true |

### 14.2 POI 过滤测试

必须测试：

- 未营业 POI 不进入路线。
- 超预算 POI 被过滤或强扣分。
- 排队超过硬阈值的 POI 被过滤。
- 不符合用户避免项的 POI 被过滤。

### 14.3 路线校验测试

必须测试：

- 总时间不超过 end_time。
- 总预算不超过硬预算。
- 必选类别被覆盖。
- 必去点被包含。
- 所有 POI 都存在。
- 所有 POI 到达时营业。

### 14.4 重规划测试

必须测试：

| 用户反馈 | 期望结果 |
|---|---|
| 少排队 | 总排队时间下降 |
| 更省钱 | 总预算下降 |
| 少走路 | 步行距离下降 |
| 下雨了 | 户外 POI 减少 |
| 只剩 2 小时 | 路线总时长压缩 |

### 14.5 解释一致性测试

要求：

- 解释中提到的理由必须来自 score_breakdown、POI 属性或 UGC 标签。
- 不能出现不存在的 POI。
- 不能出现未验证的价格、团购、营业状态。

---

## 15. 开发阶段规划

### Phase 1：基础 Harness 和数据结构

目标：跑通完整 Agent 流程。

任务：

- 创建项目结构。
- 定义 Pydantic schema。
- 创建本地 POI JSON。
- 创建本地 UGC JSON。
- 实现 AgentRunState。
- 实现状态机。
- 实现工具注册器。

交付：

- 可运行 FastAPI 后端。
- 基础测试通过。

### Phase 2：路线规划核心能力

目标：能生成可执行路线。

任务：

- 实现 parse_intent。
- 实现 retrieve_pois。
- 实现 analyze_ugc。
- 实现 score_pois。
- 实现 optimize_route。
- 实现 validate_route。

交付：

- POST /api/plan-route 可返回完整路线。

### Phase 3：动态重规划

目标：支持用户调整。

任务：

- 实现事件分类。
- 实现 minor_replan。
- 实现 partial_replan。
- 实现 full_replan。
- 实现 repair_route。

交付：

- POST /api/replan-route 可用。

### Phase 4：前端 Demo

目标：适合黑客松展示。

任务：

- 输入框。
- 路线总览卡。
- 时间轴。
- POI 卡片。
- 动态调整按钮。
- 替代方案展示。

交付：

- 可演示的 Web 页面。

### Phase 5：答辩优化

目标：增强演示效果。

任务：

- 准备 3 个典型场景。
- 增加 mock 数据质量。
- 优化推荐解释。
- 增加失败修复展示。
- 增加少排队、雨天、省钱对比。

---

## 16. 推荐项目目录结构

```text
ai-local-route-agent/
  backend/
    app/
      main.py
      api/
        routes.py
      schemas/
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
      RouteTimeline.tsx
      RouteSummary.tsx
      PoiCard.tsx
      ReplanButtons.tsx
      ExplanationPanel.tsx
  README.md
```

---

## 17. Codex 开发提示词

```text
请基于 Harness Engineering 思路，开发一个 AI 本地路线智能规划 Agent 的 MVP。

核心原则：
1. LLM 不直接生成路线，只负责意图解析、工具调度和解释。
2. 路线由确定性的 POI 召回、评分、优化和验证模块生成。
3. 系统必须包含状态机、工具注册、约束校验和动态重规划。
4. 数据先使用本地 JSON，不接真实美团接口。
5. 所有模块都要有 Pydantic schema 和 pytest 测试。

顶层状态机包括：
IDLE、UNDERSTANDING、NEED_CLARIFICATION、PLANNING、VALIDATING、REPAIRING、PRESENTING、WAITING_FOR_FEEDBACK、REPLANNING、FAILED、COMPLETED。

请实现以下目录：
- backend/app/harness/
- backend/app/tools/
- backend/app/schemas/
- backend/app/data/
- backend/tests/

请实现以下模块：
1. harness/orchestrator.py
2. harness/state_machine.py
3. harness/tool_registry.py
4. tools/intent_parser.py
5. tools/context_provider.py
6. tools/poi_retriever.py
7. tools/ugc_analyzer.py
8. tools/poi_scorer.py
9. tools/route_optimizer.py
10. tools/route_validator.py
11. tools/route_replanner.py
12. tools/explanation_generator.py

请实现 API：
- POST /api/plan-route
- POST /api/replan-route
- POST /api/explain-route

请先用 mock LLM 和本地 JSON 数据跑通完整流程：
用户自然语言输入 → 结构化意图 → POI 召回 → POI 评分 → 路线生成 → 约束校验 → 推荐解释 → 动态重规划。

请保证：
- 不输出不存在的 POI。
- 不安排未营业 POI。
- 不超过时间预算。
- 不超过硬预算。
- 每条推荐理由必须来自 POI 属性、UGC 标签或评分结果。
- 如果路线校验失败，自动尝试修复或返回明确错误。
```

---

## 18. 黑客松演示场景

### 场景 1：外地游客半日游

输入：

```text
我下午 2 点从新街口出发，晚上 8 点前回酒店。想吃南京本地菜，不想排太久，人均 150，还想拍照和喝咖啡。
```

展示：

- 主路线。
- 少排队版。
- 省钱版。
- 咖啡替代点。

### 场景 2：情侣夜游

输入：

```text
晚上想安排一个适合情侣的路线，想吃饭、拍照、看夜景，不想太赶。
```

展示：

- 氛围型路线。
- 夜景推荐理由。
- 拍照标签。

### 场景 3：亲子雨天方案

输入：

```text
下雨了，带小孩，不想去户外，想安排吃饭和一个室内活动。
```

展示：

- 室内 POI 替换。
- 亲子友好标签。
- 雨天适配解释。

---

## 19. 验收标准

### 19.1 功能验收

必须满足：

- 能解析用户自然语言。
- 能返回结构化 intent。
- 能召回候选 POI。
- 能生成路线。
- 能校验路线。
- 能解释路线。
- 能动态重规划。

### 19.2 质量验收

必须满足：

- 不输出不存在的 POI。
- 不安排未营业 POI。
- 不超过硬时间预算。
- 不超过硬预算。
- 推荐理由可追溯。
- 重规划后路线仍可执行。

### 19.3 Demo 验收

必须展示：

- 一次完整路线生成。
- 一次少排队调整。
- 一次雨天调整。
- 一次解释问答。

---

## 20. 最终技术叙事

答辩时可以这样说：

```text
我们没有把大模型当作直接生成路线的黑箱，而是采用 Harness Engineering 思路，把 LLM 放入一个可控的工程外壳中。

LLM 负责理解用户意图和生成解释；Harness 负责状态机、工具调度、上下文管理、POI 检索、UGC 分析、路线评分、约束验证和动态重规划。

这样既保留了大模型的自然语言交互能力，又避免了路线规划中的幻觉、不可执行和难以复现问题。

最终系统输出的是一条可执行、低踩雷、可消费闭环、可实时调整的本地吃喝玩乐路线。
```

---

## 21. 最终一句话

**本项目的 Agent 应设计为一个可控非线性的 Harness Agent：顶层用分层状态机管理任务生命周期，中层用 DAG 编排 POI 召回、UGC 分析、评分和优化，底层用 Validator 保证路线可执行，并用事件驱动 Replanner 支持实时动态调整。**

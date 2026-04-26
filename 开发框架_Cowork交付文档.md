# AI 本地路线智能规划系统 · 开发框架文档

> **本文档面向工程实施，描述项目的目录结构、技术栈、模块边界、接口契约、数据规格与开发顺序。所有规格均为强约束，模块开发须严格遵守接口契约以保证联调一致性。**

---

## 0. 文档使用指引

**适用对象**:本文档面向负责搭建项目脚手架、实现核心模块、做联调的开发者(含 AI Coding Agent 如 Cowork)。

**阅读顺序**:第 1 章总览 → 第 2 章技术栈 → 第 3 章目录结构(直接动手搭)→ 第 4 章数据模型 → 第 5 章模块规格(逐个实现)→ 第 6 章前端规格 → 第 7 章开发顺序 → 第 8 章联调与验收。

**强制约束**:第 4 章的数据 schema、第 5 章的模块接口签名是模块间的契约,**不允许在实现时擅自修改字段名、字段类型、返回结构**。如需变更,需同步更新本文档。

**项目代号**:`local-route-agent`(下文均使用此代号)。

---

## 1. 项目总览

### 1.1 项目目标

构建一个本地路线智能规划系统的 MVP 产品,在 4 周内完成可演示版本。核心能力:

1. 用户输入出行需求(城市+时间+人群标签),系统返回个性化 POI 推荐池
2. 用户从推荐池勾选感兴趣的 POI,系统调用约束求解算法,生成 2-3 个风格化路线方案
3. 每个方案展示为地图+时间轴+UGC 证据归因
4. 支持对话式调整(如"换一家不排队的""加一个咖啡馆")

### 1.2 技术形态

- **形态**: 前后端分离的 Web 应用,响应式适配桌面与移动端
- **后端**: Python (FastAPI) 提供 REST API
- **前端**: React + TypeScript,地图组件
- **数据**: PostgreSQL (结构化) + 向量数据库 (Chroma 或 Qdrant)
- **AI**: 调用 LLM API (Claude / OpenAI / Qwen / DeepSeek 任选其一)
- **部署**: Docker Compose 一键启动

### 1.3 范围边界(明确不做的)

为控制工作量,以下功能**明确不在 MVP 范围**:

- 用户注册/登录系统(用 mock user_id 模拟)
- 多城市数据(只覆盖 1 个城市,推荐选上海或开发者最熟悉的城市)
- 真实支付/预订接入
- 多人协同/社交分享/找搭子
- 长图导出/海报生成
- 真实排队 API 接入(用静态预估值)
- 真实 GPS 跟踪(用模拟轨迹)

---

## 2. 技术栈与依赖

### 2.1 后端

```
语言:        Python 3.11+
Web 框架:    FastAPI 0.110+
ORM:        SQLAlchemy 2.0
数据库:      PostgreSQL 15
向量库:      Chroma (开发友好) 或 Qdrant (性能更好)
LLM SDK:    anthropic / openai / dashscope (任选一个为主)
求解器:      自实现贪心算法 (备选 OR-Tools 9.x)
地图 API:    高德 Web 服务 API (推荐) / 百度地图 API
缓存:        Redis 7 (可选,MVP 可省)
```

### 2.2 前端

```
语言:        TypeScript 5.x
框架:        React 18
构建:        Vite
路由:        React Router 6
状态:        Zustand (轻量) 或 React Context
UI 库:       shadcn/ui + Tailwind CSS
地图组件:    高德地图 React 组件 (@amap/amap-jsapi-loader)
HTTP:       axios
图表:        Recharts (如有数据可视化需要)
```

### 2.3 开发工具

```
代码格式化:  black + isort (Python),prettier (TS)
类型检查:    mypy (Python),tsc (TS)
环境管理:    uv 或 poetry (Python),pnpm (Node)
容器化:      Docker + Docker Compose
版本控制:    Git,要求 PR + Code Review 流程
```

### 2.4 必须的环境变量

在项目根目录的 `.env` 文件中定义(`.env.example` 提供模板):

```bash
# LLM 配置
LLM_PROVIDER=anthropic          # anthropic | openai | qwen
LLM_API_KEY=sk-xxx
LLM_MODEL=claude-opus-4-7

# 数据库
DATABASE_URL=postgresql://user:pass@localhost:5432/local_route
VECTOR_DB_PATH=./data/chroma

# 地图 API
AMAP_KEY=xxx
AMAP_SECURITY_CODE=xxx          # 仅前端需要

# 应用
APP_PORT=8000
FRONTEND_PORT=5173
DEFAULT_CITY=shanghai           # MVP 默认城市
```

---

## 3. 项目目录结构

### 3.1 根目录

```
local-route-agent/
├── backend/                  # 后端服务
├── frontend/                 # 前端应用
├── data/                     # 数据文件(POI、UGC 处理产物)
├── scripts/                  # 一次性脚本(数据爬取、UGC 预处理)
├── docs/                     # 项目文档
├── docker-compose.yml        # 一键启动
├── .env.example              # 环境变量模板
├── .gitignore
└── README.md
```

### 3.2 后端目录(`backend/`)

```
backend/
├── app/
│   ├── main.py                  # FastAPI 入口
│   ├── config.py                # 配置加载
│   ├── deps.py                  # 依赖注入
│   │
│   ├── api/                     # API 路由层
│   │   ├── __init__.py
│   │   ├── routes_pool.py       # 推荐池 API
│   │   ├── routes_plan.py       # 方案生成 API
│   │   ├── routes_chat.py       # 对话调整 API
│   │   └── routes_meta.py       # 元数据 API (城市、标签等)
│   │
│   ├── models/                  # 数据库 ORM 模型
│   │   ├── __init__.py
│   │   ├── poi.py
│   │   ├── ugc.py
│   │   └── user_profile.py
│   │
│   ├── schemas/                 # Pydantic 请求/响应模型
│   │   ├── __init__.py
│   │   ├── pool.py
│   │   ├── plan.py
│   │   └── common.py
│   │
│   ├── services/                # 业务逻辑层(核心)
│   │   ├── __init__.py
│   │   ├── pool_service.py      # 推荐池生成
│   │   ├── intent_service.py    # 意图理解 (LLM)
│   │   ├── solver_service.py    # 约束求解 (算法)
│   │   ├── plan_service.py      # 方案润色 (LLM)
│   │   ├── chat_service.py      # 对话调整
│   │   ├── ugc_service.py       # UGC 检索与摘要
│   │   └── profile_service.py   # 用户画像
│   │
│   ├── repositories/            # 数据访问层
│   │   ├── __init__.py
│   │   ├── poi_repo.py
│   │   ├── ugc_repo.py
│   │   └── vector_repo.py       # 向量库访问
│   │
│   ├── llm/                     # LLM 调用封装
│   │   ├── __init__.py
│   │   ├── client.py            # 统一 LLM 客户端
│   │   └── prompts/             # Prompt 模板目录
│   │       ├── intent.py
│   │       ├── plan_refine.py
│   │       └── chat_adjust.py
│   │
│   ├── solver/                  # 求解算法
│   │   ├── __init__.py
│   │   ├── greedy.py            # 贪心算法 (主)
│   │   ├── distance.py          # 距离矩阵计算
│   │   └── styles.py            # 风格化策略
│   │
│   └── utils/                   # 工具函数
│       ├── __init__.py
│       ├── time_utils.py
│       └── geo_utils.py
│
├── tests/                       # 单测
├── alembic/                     # 数据库迁移
├── pyproject.toml
└── README.md
```

### 3.3 前端目录(`frontend/`)

```
frontend/
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── router.tsx
│   │
│   ├── pages/                   # 页面级组件
│   │   ├── HomePage.tsx         # 首页(输入)
│   │   ├── PoolPage.tsx         # 推荐池页
│   │   ├── PlanPage.tsx         # 方案展示页
│   │   └── ChatPage.tsx         # 对话调整页
│   │
│   ├── components/              # 通用组件
│   │   ├── PoiCard.tsx          # POI 卡片
│   │   ├── PoolGrid.tsx         # 推荐池网格
│   │   ├── PlanTimeline.tsx     # 时间轴视图
│   │   ├── PlanMap.tsx          # 地图视图
│   │   ├── PlanCompare.tsx      # 方案对比
│   │   ├── UgcEvidence.tsx      # UGC 证据展示
│   │   ├── TagSelector.tsx      # 标签选择器
│   │   └── ui/                  # shadcn 组件
│   │
│   ├── hooks/
│   │   ├── usePool.ts
│   │   ├── usePlan.ts
│   │   └── useChat.ts
│   │
│   ├── store/                   # Zustand 全局状态
│   │   ├── userStore.ts
│   │   ├── poolStore.ts
│   │   └── planStore.ts
│   │
│   ├── api/                     # API 客户端
│   │   ├── client.ts
│   │   ├── pool.ts
│   │   ├── plan.ts
│   │   └── chat.ts
│   │
│   ├── types/                   # TypeScript 类型(与后端 schema 对齐)
│   │   ├── poi.ts
│   │   ├── plan.ts
│   │   └── user.ts
│   │
│   └── styles/
│       └── globals.css
│
├── public/
├── package.json
├── vite.config.ts
├── tsconfig.json
└── README.md
```

### 3.4 数据目录(`data/`)

```
data/
├── raw/                         # 原始数据(爬取得来,不入版本控制)
│   ├── poi_shanghai.json
│   └── ugc_reviews/
│
├── processed/                   # 预处理后的数据(可入版本控制)
│   ├── poi_enriched.json        # POI + 结构化属性
│   └── ugc_extracted.json       # UGC 提取的隐性约束
│
├── chroma/                      # 向量库持久化
│
└── seed.sql                     # 数据库种子数据
```

---

## 4. 数据模型(强约束)

> **本章定义的所有数据结构是模块间通信的契约,实现时必须严格遵守字段名与类型。**

### 4.1 数据库表

#### 4.1.1 `pois` 表

```sql
CREATE TABLE pois (
    id              VARCHAR(64) PRIMARY KEY,        -- 业务 ID,如 "sh_poi_001"
    name            VARCHAR(255) NOT NULL,
    city            VARCHAR(64) NOT NULL,
    category        VARCHAR(64) NOT NULL,           -- 见 4.2 枚举
    sub_category    VARCHAR(64),                    -- 细分类
    address         VARCHAR(512),
    latitude        DECIMAL(10, 7) NOT NULL,
    longitude       DECIMAL(10, 7) NOT NULL,
    rating          DECIMAL(3, 2),                  -- 0.00 ~ 5.00
    price_per_person INTEGER,                       -- 人均(分)
    open_hours      JSONB,                          -- 见 4.3 schema
    tags            JSONB,                          -- 字符串数组
    cover_image     VARCHAR(512),
    review_count    INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_pois_city ON pois(city);
CREATE INDEX idx_pois_category ON pois(category);
CREATE INDEX idx_pois_rating ON pois(rating DESC);
```

#### 4.1.2 `poi_enriched` 表(UGC 提取后的扩展属性)

```sql
CREATE TABLE poi_enriched (
    poi_id              VARCHAR(64) PRIMARY KEY REFERENCES pois(id),

    -- UGC 提取的隐性约束
    queue_estimate      JSONB,         -- {weekday_peak: 30, weekend_peak: 60}, 单位分钟
    visit_duration      INTEGER,       -- 推荐停留时长(分钟)
    best_time_slots     JSONB,         -- 字符串数组,如 ["weekday_afternoon", "weekend_morning"]
    avoid_time_slots    JSONB,         -- 同上格式

    -- UGC 摘要(给前端展示)
    highlight_quotes    JSONB,         -- 至多 3 条 UGC 金句,见 4.3 schema
    high_freq_keywords  JSONB,         -- [{keyword: "位置好找", count: 308}, ...]
    hidden_menu         JSONB,         -- 字符串数组
    avoid_tips          JSONB,         -- 字符串数组(避雷点)

    -- 适配场景标签(LLM 推断)
    suitable_for        JSONB,         -- 如 ["couple", "parent_child", "solo", "friends"]
    atmosphere          JSONB,         -- 如 ["quiet", "lively", "photogenic"]

    updated_at          TIMESTAMP DEFAULT NOW()
);
```

#### 4.1.3 `ugc_reviews` 表

```sql
CREATE TABLE ugc_reviews (
    id              SERIAL PRIMARY KEY,
    poi_id          VARCHAR(64) NOT NULL REFERENCES pois(id),
    content         TEXT NOT NULL,
    rating          INTEGER,              -- 1-5
    review_date     DATE,
    source          VARCHAR(32),          -- "dianping" | "xiaohongshu" | "meituan"
    embedding_id    VARCHAR(64),          -- 关联向量库 ID
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_ugc_poi ON ugc_reviews(poi_id);
CREATE INDEX idx_ugc_date ON ugc_reviews(review_date DESC);
```

#### 4.1.4 `user_profiles` 表(MVP 简化版)

```sql
CREATE TABLE user_profiles (
    user_id         VARCHAR(64) PRIMARY KEY,
    persona_tags    JSONB,         -- ["foodie", "photographer", "parent"]
    pace_preference VARCHAR(32),   -- "efficient" | "relaxed" | "balanced"
    budget_level    VARCHAR(32),   -- "low" | "mid" | "high"
    avoid_categories JSONB,        -- 不喜欢的 POI 类别
    history_summary JSONB,         -- 简单的历史行为摘要
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);
```

### 4.2 关键枚举

```python
# POI 类别
POI_CATEGORIES = [
    "restaurant",      # 餐饮
    "cafe",            # 咖啡
    "scenic",          # 景点
    "shopping",        # 购物
    "entertainment",   # 娱乐
    "culture",         # 文化(博物馆、展览)
    "outdoor",         # 户外
    "nightlife",       # 夜生活
]

# 人群标签(persona)
PERSONA_TAGS = [
    "foodie",          # 探店达人
    "local_gourmet",   # 本地老饕
    "photographer",    # 打卡拍照
    "literary",        # 文艺青年
    "parent_child",    # 亲子家庭
    "couple",          # 情侣约会
    "friends",         # 朋友聚会
    "solo",            # 独自出行
]

# 出行风格
PACE_STYLES = [
    "efficient",       # 高效型
    "relaxed",         # 松弛型
    "balanced",        # 平衡型
]

# 时间段
TIME_SLOTS = [
    "weekday_morning",     "weekday_noon",     "weekday_afternoon",     "weekday_evening",
    "weekend_morning",     "weekend_noon",     "weekend_afternoon",     "weekend_evening",
]

# 方案风格
PLAN_STYLES = [
    "efficient",       # 高效打卡型
    "relaxed",         # 松弛漫游型
    "foodie_first",    # 美食优先型
]
```

### 4.3 关键 JSON Schema

#### 4.3.1 营业时间(`pois.open_hours`)

```json
{
  "monday":    [{"open": "10:00", "close": "22:00"}],
  "tuesday":   [{"open": "10:00", "close": "22:00"}],
  "wednesday": null,
  "thursday":  [{"open": "10:00", "close": "22:00"}],
  "friday":    [{"open": "10:00", "close": "23:00"}],
  "saturday":  [{"open": "09:00", "close": "23:00"}],
  "sunday":    [{"open": "09:00", "close": "22:00"}]
}
```

`null` 表示当日休息。一天可有多个营业段(如午休)。

#### 4.3.2 UGC 金句(`poi_enriched.highlight_quotes`)

```json
[
  {
    "quote": "下午3点最安静,适合带电脑工作",
    "source": "dianping",
    "review_date": "2025-09-12",
    "category": "time_recommendation"
  },
  {
    "quote": "二楼靠窗位置最好,但要提前预订",
    "source": "xiaohongshu",
    "review_date": "2025-10-05",
    "category": "spatial_tip"
  }
]
```

`category` 枚举:`time_recommendation` | `spatial_tip` | `dish_recommendation` | `avoid_warning` | `general_praise`

---

## 5. 模块规格

> **本章定义后端各 Service 的输入输出契约。所有签名严格遵守,不得修改字段名与类型。**

### 5.1 PoolService(推荐池服务)

**职责**: 接收用户请求,产出个性化的 POI 推荐池(15-20 个候选)。

**核心方法**:

```python
class PoolService:
    def generate_pool(
        self,
        request: PoolRequest
    ) -> PoolResponse:
        """生成推荐池"""
        ...
```

**输入 schema**:

```python
class PoolRequest(BaseModel):
    user_id: str                          # 用户 ID(MVP 用 mock 即可)
    city: str                             # 城市,如 "shanghai"
    date: str                             # 日期,YYYY-MM-DD
    time_window: TimeWindow               # 时间窗
    persona_tags: List[str]               # 至少 1 个 persona 标签
    pace_style: Optional[str] = None      # 出行风格
    party: Optional[str] = None           # 同行人群,如 "couple", "with_kids"
    budget_per_person: Optional[int] = None  # 人均预算(元)
    free_text: Optional[str] = None       # 自然语言补充

class TimeWindow(BaseModel):
    start: str   # HH:MM
    end: str     # HH:MM
```

**输出 schema**:

```python
class PoolResponse(BaseModel):
    pool_id: str                          # 池 ID,后续操作引用
    categories: List[PoolCategory]        # 分类组织的候选
    default_selected_ids: List[str]       # 智能默认勾选的 POI ID
    meta: PoolMeta

class PoolCategory(BaseModel):
    name: str                             # 分类名,如 "必去经典"、"小众宝藏"
    description: str
    pois: List[PoiInPool]

class PoiInPool(BaseModel):
    id: str
    name: str
    category: str
    rating: float
    price_per_person: Optional[int]
    cover_image: Optional[str]
    distance_meters: Optional[int]        # 距用户起点距离
    why_recommend: str                    # 一句话推荐理由(LLM 生成)
    highlight_quote: Optional[str]        # 一条 UGC 金句
    keywords: List[str]                   # 高频关键词,至多 5 个
    estimated_queue_min: Optional[int]    # 预估排队(基于时段)
    suitable_score: float                 # 0-1,与用户匹配度

class PoolMeta(BaseModel):
    total_count: int
    generated_at: datetime
    user_persona_summary: str             # 给用户看的画像摘要
```

**实现要点**:

1. 第一步从数据库召回候选(规则过滤:城市、营业时间、评分阈值)
2. 第二步向量检索增强(基于 persona 和 free_text 的语义召回)
3. 第三步排序(融合评分:rating × 0.3 + persona_match × 0.5 + popularity × 0.2)
4. 第四步分类(按 category + UGC 标签划分到"必去经典 / 小众宝藏 / 此刻热门 / 季节限定")
5. 第五步用 LLM 给每个 POI 生成 `why_recommend` 一句话理由(批量调用,不要逐个调用)
6. 第六步选出 default_selected_ids(取每分类的 Top 1,共 3-5 个)

**性能要求**: 整个流程在 5 秒内返回(包含 LLM 调用)。LLM 批处理时一次最多 10 个 POI。

### 5.2 IntentService(意图理解服务)

**职责**: 把用户的自然语言+勾选的 POI 列表,翻译成结构化的规划任务。

```python
class IntentService:
    def parse_intent(
        self,
        user_id: str,
        selected_poi_ids: List[str],
        free_text: Optional[str],
        context: PlanContext
    ) -> StructuredIntent:
        """意图解析"""
        ...

class PlanContext(BaseModel):
    city: str
    date: str
    time_window: TimeWindow
    party: Optional[str]
    budget_per_person: Optional[int]

class StructuredIntent(BaseModel):
    hard_constraints: HardConstraints
    soft_preferences: SoftPreferences
    must_visit_pois: List[str]            # 必去 POI ID
    avoid_pois: List[str]                 # 避免 POI ID

class HardConstraints(BaseModel):
    start_time: str                       # HH:MM
    end_time: str                         # HH:MM
    budget_total: Optional[int]
    transport_mode: str                   # "walking" | "driving" | "transit" | "mixed"
    must_include_meal: bool               # 是否必须包含正餐

class SoftPreferences(BaseModel):
    pace: str                             # "efficient" | "relaxed" | "balanced"
    avoid_queue: bool                     # 是否避开排队
    weather_sensitive: bool               # 是否对天气敏感
    photography_priority: bool            # 是否优先适合拍照
    food_diversity: bool                  # 是否要求口味多样
    custom_notes: List[str]               # LLM 提取的其他自由文本备注
```

**实现要点**:

1. 主要靠 LLM 完成,Prompt 模板见 `app/llm/prompts/intent.py`
2. 用 Function Calling 或 JSON Mode 强制结构化输出
3. 失败重试 1 次,仍失败时返回保守的默认值,**不能阻塞流程**

### 5.3 SolverService(约束求解服务)

**职责**: 基于结构化意图和候选 POI,产出多个风格化的路线骨架。**这一层完全不调用 LLM**。

```python
class SolverService:
    def solve(
        self,
        intent: StructuredIntent,
        candidate_poi_ids: List[str]
    ) -> List[RouteSkeleton]:
        """求解多个风格化路线"""
        ...

class RouteSkeleton(BaseModel):
    style: str                            # "efficient" | "relaxed" | "foodie_first"
    stops: List[RouteStop]                # 按顺序的站点
    dropped_poi_ids: List[str]            # 被砍掉的 POI ID(候选中没用上的)
    drop_reasons: Dict[str, str]          # poi_id -> 砍掉理由
    metrics: RouteMetrics

class RouteStop(BaseModel):
    poi_id: str
    arrival_time: str                     # HH:MM
    departure_time: str                   # HH:MM
    duration_min: int
    transport_to_next: Optional[Transport]

class Transport(BaseModel):
    mode: str                             # "walking" | "driving" | "transit"
    duration_min: int
    distance_meters: int

class RouteMetrics(BaseModel):
    total_duration_min: int
    total_cost: int                       # 估算总花费
    poi_count: int
    walking_distance_meters: int
    queue_total_min: int                  # 总排队时间预估
```

**实现策略(MVP 推荐)**:

> **不要直接上 OR-Tools,本地短链场景下贪心+局部交换够用,且更可控。**

伪代码:

```python
def greedy_solve(intent, candidates, style: str) -> RouteSkeleton:
    # 1. 根据风格调整候选权重
    weights = compute_weights(candidates, style, intent)

    # 2. 选起始 POI(高权重 + 早营业)
    current = pick_start(candidates, weights, intent.start_time)
    route = [current]
    used_time = poi_duration(current)
    used_budget = poi_cost(current)

    # 3. 贪心扩展
    while True:
        next_poi = pick_next(
            current=current,
            candidates=remaining,
            weights=weights,
            time_left=intent.end_time - current_time(),
            budget_left=intent.budget - used_budget,
            constraints=intent.hard_constraints
        )
        if not next_poi:
            break
        route.append(next_poi)
        used_time += transport_time + poi_duration(next_poi)
        used_budget += poi_cost(next_poi)

    # 4. 局部 2-opt 交换优化(交换两站顺序看总通勤是否更短)
    route = local_search_2opt(route)

    # 5. 生成时间窗
    skeleton = generate_time_windows(route, intent.start_time)

    return skeleton
```

风格化策略(`app/solver/styles.py`):

| 风格 | 权重调整 | 站点数偏好 | 选 POI 倾向 |
|---|---|---|---|
| efficient | category 多样性 ×1.5,站点数 ×1.2 | 5-6 | 评分稳定、热门 |
| relaxed | 单点停留 ×1.5,通勤短 ×1.3 | 3-4 | 慢节奏场所 |
| foodie_first | 餐厅 ×2.0 | 4-5 | 优先安排正餐 |

**实现要点**:

1. 距离矩阵预先计算(`app/solver/distance.py`),首选高德 API,备选用经纬度直线距离 × 1.3
2. 营业时间检查必须严格(POI 关门时不能安排访问)
3. 三个风格的方案应该有可见的差异,**至少 30% 的站点不同或顺序不同**
4. 求解失败(无可行解)时返回最佳的部分解,标记 `dropped_poi_ids`,**不能抛异常**

### 5.4 PlanService(方案润色服务)

**职责**: 把求解器输出的冷冰冰的路线骨架,润色成用户可读的方案。

```python
class PlanService:
    def refine_plans(
        self,
        skeletons: List[RouteSkeleton],
        intent: StructuredIntent,
        context: PlanContext
    ) -> List[RefinedPlan]:
        """润色多方案"""
        ...

class RefinedPlan(BaseModel):
    plan_id: str
    style: str
    title: str                            # 如"米其林漫步""周末松弛系"
    description: str                      # 一句话描述
    stops: List[RefinedStop]
    summary: PlanSummary

class RefinedStop(BaseModel):
    poi_id: str
    poi_name: str
    arrival_time: str
    departure_time: str
    why_this_one: str                     # 为什么是它(引用 UGC)
    ugc_evidence: List[UgcSnippet]        # 至多 2 条 UGC 证据
    risk_warning: Optional[str]           # 风险提示(如排队)
    transport_to_next: Optional[Transport]

class UgcSnippet(BaseModel):
    quote: str
    source: str
    date: Optional[str]

class PlanSummary(BaseModel):
    total_duration_min: int
    total_cost: int
    poi_count: int
    style_highlights: List[str]           # 该风格的核心特点
    tradeoffs: List[str]                  # 这个方案牺牲了什么
    dropped_pois: List[DroppedPoi]

class DroppedPoi(BaseModel):
    poi_id: str
    poi_name: str
    reason: str
```

**实现要点**:

1. 用一次 LLM 调用,输入是 N 个 RouteSkeleton + POI 详情 + 用户意图,输出 N 个 RefinedPlan
2. UGC 证据从 `poi_enriched.highlight_quotes` 中选取最相关的(根据意图的关键词匹配)
3. `tradeoffs` 字段必须明确填写,不能空(这是体现"AI 帮你决定"的关键)
4. `title` 和 `description` 要有差异化,避免三个方案听起来一样

### 5.5 ChatService(对话调整服务)

**职责**: 接收用户的自然语言修改指令,调整既有方案。

```python
class ChatService:
    def adjust_plan(
        self,
        plan_id: str,
        user_message: str,
        chat_history: List[ChatTurn]
    ) -> ChatResponse:
        """对话调整"""
        ...

class ChatTurn(BaseModel):
    role: str                             # "user" | "assistant"
    content: str
    timestamp: datetime

class ChatResponse(BaseModel):
    intent_type: str                      # 见下文枚举
    updated_plan: Optional[RefinedPlan]   # 调整后的方案
    assistant_message: str                # 给用户的回复
    requires_confirmation: bool           # 是否需要用户确认后才应用
```

**支持的调整意图(MVP 至少实现前 4 个)**:

```python
ADJUSTMENT_INTENTS = [
    "replace_poi",         # 替换某站(如"换一家不排队的")
    "add_poi",             # 增加一站(如"加一杯咖啡")
    "remove_poi",          # 删除一站(如"跳过下一站")
    "compress_time",       # 压缩时间(如"剩下能不能快点")
    "extend_time",         # 延长时间(可选)
    "change_style",        # 切换风格(可选)
]
```

**实现要点**:

1. 第一步用 LLM 解析意图类型和参数(替换哪站、加什么类型等)
2. 第二步根据意图类型分发到不同处理器:
   - `replace_poi` → 检索相似 POI(向量库 + 距离过滤),选 top 1 替换,重新走求解器
   - `add_poi` → 在合理位置插入,重新走求解器
   - `remove_poi` → 直接删除,重新分配时间
   - `compress_time` → 砍站点或压缩单点时长,重新走求解器
3. 任何调整都要保证物理可行(时间窗、营业时间)
4. `requires_confirmation` 默认为 `false`,只在大规模调整(如砍超过 2 站)时设 `true`

### 5.6 UgcService(UGC 检索服务)

**职责**: 提供 UGC 的检索、摘要、相似度计算等基础能力。

```python
class UgcService:
    def search_similar_pois(
        self,
        reference_poi_id: str,
        query_text: Optional[str],
        top_k: int = 5
    ) -> List[Tuple[str, float]]:
        """基于 UGC 相似度找相似 POI(用于替换场景)"""
        ...

    def get_highlight_quotes(
        self,
        poi_id: str,
        intent_keywords: List[str],
        max_count: int = 2
    ) -> List[UgcSnippet]:
        """获取与意图相关的 UGC 金句"""
        ...

    def estimate_queue(
        self,
        poi_id: str,
        target_datetime: datetime
    ) -> int:
        """估算指定时间点的排队时长(分钟)"""
        ...
```

### 5.7 ProfileService(用户画像服务)

**职责**: 管理用户画像的读取、更新。MVP 阶段简化实现。

```python
class ProfileService:
    def get_profile(self, user_id: str) -> UserProfile:
        """读取画像。新用户返回默认画像。"""
        ...

    def update_from_tags(self, user_id: str, persona_tags: List[str]):
        """从标签速选更新画像"""
        ...

    def update_from_selections(self, user_id: str, selected_poi_ids: List[str]):
        """从勾选行为更新画像(简化版:统计类别分布)"""
        ...
```

---

## 6. 前端规格

### 6.1 页面流转

```
首页 (HomePage)
  └─ 输入城市、日期、时间窗、persona 标签
     └─ [生成推荐池] 按钮 → 调用 POST /api/pool/generate
        └─ 跳转到 推荐池页 (PoolPage)

推荐池页 (PoolPage)
  └─ 分类展示 POI 网格,每个 PoiCard 可勾选
  └─ 显示已勾选数量、提醒缺失维度(如"还没选餐厅")
     └─ [生成方案] 按钮 → 调用 POST /api/plan/generate
        └─ 跳转到 方案页 (PlanPage)

方案页 (PlanPage)
  └─ 顶部:三个方案卡片(可切换)
  └─ 主区:地图视图 + 时间轴视图(可切换)
  └─ 每个站点可点击查看 UGC 证据
  └─ 底部:对话框入口
     └─ 点击"调整" → 跳转或弹出 ChatPage

对话调整 (ChatPage 或 Modal)
  └─ 用户输入指令 → 调用 POST /api/chat/adjust
  └─ 返回更新后的 plan,前端重新渲染方案
```

### 6.2 关键组件规格

#### 6.2.1 `<PoiCard>`

**Props**:
```typescript
interface PoiCardProps {
  poi: PoiInPool;
  selected: boolean;
  onToggle: (poiId: string) => void;
  showWhyRecommend?: boolean;     // 是否展示推荐理由
  compact?: boolean;              // 紧凑模式
}
```

**视觉要求**:
- 卡片尺寸:桌面 240×320,移动 100% 宽 × 自适应
- 必须展示:封面图、名称、评分、人均、距离、推荐理由(1 句话)、UGC 金句(1 句)
- 勾选状态用边框高亮 + 角标 ✓
- 点击空白处切换勾选,点击图片打开详情

#### 6.2.2 `<PoolGrid>`

**Props**:
```typescript
interface PoolGridProps {
  pool: PoolResponse;
  selectedIds: Set<string>;
  onSelectionChange: (ids: Set<string>) => void;
}
```

**布局**:
- 按 `categories` 分块渲染,每块一个标题(如"必去经典")
- 桌面 4 列网格,平板 3 列,移动 2 列
- 每个分类内卡片左右滑动(移动端)或网格(桌面)

**关键交互**:
- 默认勾选 `default_selected_ids` 中的 POI
- 顶部显示已勾选数量 + 智能提醒(如"已选 5 个,但还没有餐厅,要不要加一家?")

#### 6.2.3 `<PlanMap>`

**Props**:
```typescript
interface PlanMapProps {
  plan: RefinedPlan;
  highlightedStopIndex?: number;
  onStopClick?: (index: number) => void;
}
```

**视觉要求**:
- 用高德地图组件渲染
- 用编号标记(1, 2, 3...)展示各站点
- 站点之间画连线(步行虚线、驾车实线)
- 高亮态用大尺寸标记 + 弹窗

#### 6.2.4 `<PlanTimeline>`

**Props**:
```typescript
interface PlanTimelineProps {
  plan: RefinedPlan;
  onStopClick?: (index: number) => void;
}
```

**视觉要求**:
- 垂直时间轴布局
- 每个站点显示:时间、POI 名称、停留时长、why_this_one
- 点击展开 UGC 证据
- 站点间显示通勤方式与时长

#### 6.2.5 `<PlanCompare>`

**Props**:
```typescript
interface PlanCompareProps {
  plans: RefinedPlan[];
  activePlanId: string;
  onSwitch: (planId: string) => void;
}
```

**视觉要求**:
- 顶部三个标签页(对应三种风格),展示 title 和核心 metric
- 切换时整个方案视图重新渲染
- **关键:必须可视化展示三个方案的差异**(如哪几站不同、总时间差、总花费差)

### 6.3 状态管理

使用 Zustand,定义三个 store:

```typescript
// userStore: 用户基础信息和画像(MVP 用 mock)
interface UserStore {
  userId: string;
  personaTags: string[];
  paceStyle: string;
  setPersonaTags: (tags: string[]) => void;
  setPaceStyle: (style: string) => void;
}

// poolStore: 当前推荐池和勾选状态
interface PoolStore {
  pool: PoolResponse | null;
  selectedIds: Set<string>;
  loading: boolean;
  fetchPool: (request: PoolRequest) => Promise<void>;
  toggleSelection: (poiId: string) => void;
  clearSelection: () => void;
}

// planStore: 当前方案集合
interface PlanStore {
  plans: RefinedPlan[];
  activePlanId: string | null;
  loading: boolean;
  generatePlans: (params: PlanRequest) => Promise<void>;
  switchPlan: (planId: string) => void;
  applyAdjustment: (response: ChatResponse) => void;
}
```

### 6.4 API 客户端

所有 API 调用走 `src/api/`,统一处理错误和 loading 状态。基础地址通过 Vite 环境变量 `VITE_API_BASE_URL` 配置。

```typescript
// src/api/client.ts
import axios from 'axios';

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 30000,    // LLM 调用可能较慢
});

apiClient.interceptors.response.use(
  (res) => res.data,
  (err) => {
    // 统一错误处理
    return Promise.reject(err);
  }
);
```

---

## 7. REST API 规格

> 所有 API 以 `/api` 为前缀,返回 JSON。错误统一格式 `{error: {code: string, message: string}}`。

### 7.1 推荐池

**`POST /api/pool/generate`**

请求体:`PoolRequest`(见 5.1)
响应体:`PoolResponse`(见 5.1)

### 7.2 方案生成

**`POST /api/plan/generate`**

请求体:
```typescript
{
  pool_id: string;
  selected_poi_ids: string[];
  free_text?: string;            // 用户的自然语言补充
  context: PlanContext;
}
```

响应体:
```typescript
{
  plans: RefinedPlan[];          // 通常 2-3 个
}
```

### 7.3 对话调整

**`POST /api/chat/adjust`**

请求体:
```typescript
{
  plan_id: string;
  user_message: string;
  chat_history: ChatTurn[];
}
```

响应体:`ChatResponse`(见 5.5)

### 7.4 元数据

**`GET /api/meta/personas`** — 返回所有 persona 标签
**`GET /api/meta/cities`** — 返回支持的城市列表(MVP 只有一个)
**`GET /api/poi/{poi_id}`** — 返回单个 POI 详情(含 enriched 数据)

---

## 8. 开发顺序与里程碑

### 8.1 第 1 周:数据底座

**目标**: 数据准备完成,支持后续模块开发。

**任务清单**:
- [ ] 项目脚手架搭建(目录、Docker Compose、CI 跑起来)
- [ ] 数据库表结构创建,Alembic 迁移配置
- [ ] 写数据爬取脚本(`scripts/crawl_pois.py`),从公开点评类网站获取 1 个城市的 100-200 个 POI
- [ ] 写 UGC 预处理脚本(`scripts/extract_ugc.py`),用 LLM 批量处理评论,提取结构化属性,写入 `poi_enriched`
- [ ] 评论 embedding 入向量库
- [ ] `seed.sql` 准备好,docker-compose up 后能直接看到数据
- [ ] LLM 客户端封装(`app/llm/client.py`)调通,能稳定返回 JSON

**验收标准**: `SELECT count(*) FROM pois` ≥ 100,`SELECT count(*) FROM poi_enriched WHERE highlight_quotes IS NOT NULL` ≥ 80。

### 8.2 第 2 周:核心链路

**目标**: 后端核心 API 跑通,前端页面骨架就绪。

**任务清单(后端)**:
- [ ] 实现 `PoolService`,跑通推荐池生成
- [ ] 实现 `IntentService`,Prompt 写好并测试
- [ ] 实现 `SolverService`(贪心算法),跑通至少 1 个风格
- [ ] 实现 `PlanService`(润色),跑通基础版
- [ ] 三个 API 端点(`/pool/generate`、`/plan/generate`、`/poi/{id}`)联通

**任务清单(前端)**:
- [ ] 项目脚手架搭建,路由、状态管理就位
- [ ] HomePage 完成(标签选择、时间选择、提交)
- [ ] PoolPage 完成(分类展示、勾选交互)
- [ ] PlanPage 骨架(单方案展示就行,先不做对比)
- [ ] API 客户端联通

**验收标准**: 端到端跑通,从首页输入到看到一个方案。**视觉先不打磨,功能先要正确。**

### 8.3 第 3 周:差异化与体验

**目标**: 把 P1 功能挂上,产品有"亮点"。

**任务清单(后端)**:
- [ ] `SolverService` 三种风格全部实现,差异明显
- [ ] `PlanService` 输出 tradeoffs、dropped_pois,UGC 证据归因正确
- [ ] `ChatService` 实现至少 4 种调整意图
- [ ] 性能优化:LLM 调用批处理、必要的缓存

**任务清单(前端)**:
- [ ] PlanCompare 组件实现,三方案切换流畅
- [ ] PlanMap 地图组件接入,站点和路线渲染正确
- [ ] PlanTimeline 时间轴优化,UGC 证据可展开
- [ ] ChatPage 对话调整 UI

**验收标准**: 三个方案的差异肉眼可见,UGC 证据在 PlanPage 上可点击查看,对话框能演示"换一家"场景。

### 8.4 第 4 周:打磨与答辩

**目标**: 演示就绪,材料完备。

**任务清单**:
- [ ] UI 视觉打磨(色彩、间距、动效)
- [ ] 异常情况处理(LLM 失败、求解失败、网络异常的兜底)
- [ ] **录制 Demo 备份视频**(3 分钟,完整展示核心流程)
- [ ] 答辩 PPT 完成
- [ ] 方案文档定稿
- [ ] 演练 3 次以上

**严格禁止**: 第 4 周不允许加新功能。任何"再加一个就更好了"的想法都按住,做完即可。

### 8.5 联调测试用例

每周末跑一次端到端测试,验证以下关键 case:

| 用例 | 输入 | 预期输出 |
|---|---|---|
| 标准流程 | 上海+周六下午+情侣+探店达人 | 推荐池 ≥15 POI,生成 3 个差异化方案 |
| 冷启动 | 不输入 persona,只输城市日期 | 默认勾选 5 个 POI,能生成方案 |
| 自由文本 | "不想排队太久,预算 300/人" | 方案中 queue_total_min ≤ 30,total_cost/poi_count ≤ 300 |
| 对话调整 | "把第二站换成不需要排队的" | 第二站被替换,新 POI 的 queue_estimate 更低 |
| 极端勾选 | 一次勾 10 个 POI | 方案合理砍到 5-6 个,dropped_pois 有理由说明 |

---

## 9. 编码规范

### 9.1 后端

- 类型注解全覆盖,关键函数加 docstring
- 所有外部调用(LLM、地图 API、数据库)必须有超时和重试
- LLM 输出必须做 schema 校验,失败时降级而非抛错
- 日志:用 `logging` 模块,关键节点(LLM 调用入参出参、求解器输入输出)记录 INFO 级
- **绝对不要在 Service 层裸调 LLM API**,必须经过 `app/llm/client.py`

### 9.2 前端

- TypeScript strict 模式,不允许 `any`
- 所有 API 响应类型与后端 schema 严格对齐(可在 `src/types/` 中维护)
- 组件优先函数式,Hook 按业务封装在 `src/hooks/`
- 加载态、错误态必须明确处理,不能让用户对着空白页发呆
- 关键交互(勾选、提交、切换方案)有视觉反馈(动画 / Toast / Loading)

### 9.3 Prompt 模板规范

所有 LLM Prompt 集中在 `app/llm/prompts/`,每个 Prompt 文件:

1. 定义清晰的输入变量(用模板字符串)
2. 顶部注释说明用途、期望输入、期望输出
3. 输出格式严格用 JSON Schema 约束
4. **不允许把 Prompt 散在 Service 代码里**

---

## 10. 联调与风险

### 10.1 关键风险与应对

| 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|
| LLM API 不稳定/限流 | 高 | 阻塞主流程 | 多 Provider 切换,失败降级到规则版 |
| 数据爬取受限 | 中 | 没有真实数据 | 准备一份手工整理的种子数据(50 POI 起步) |
| 求解器结果差 | 中 | 方案不可信 | 多写几个测试 case 反复验证 |
| 前端地图组件踩坑 | 中 | Demo 不出彩 | 第 2 周就把地图渲染跑通,别拖到最后 |
| 联调时数据 schema 对不上 | 高 | 浪费大量时间 | **严格遵守第 4-5 章的 schema** |
| 时间不够 | 高 | 砍功能 | 严格按 P0/P1/P2 优先级,P2 随时可砍 |

### 10.2 演示降级方案

如果某些功能演示当天出问题,准备好备选:

- **LLM 挂了**: 准备 3 个固定 case 的预生成结果(json 文件),前端直接读取
- **地图 API 挂了**: 准备静态地图图片备用
- **整个后端挂了**: 切换到 Demo 视频
- **网络挂了**: 本地启动一个完整副本,断网也能演示

---

## 11. 交付物清单

第 4 周末必须交付以下内容:

- [ ] 完整代码仓库(GitHub/GitLab),README 包含一键启动命令
- [ ] Docker Compose 部署成功演示
- [ ] 演示视频(3 分钟,1080P,有字幕)
- [ ] 答辩 PPT(20-25 页)
- [ ] 方案文档(本文档之外的产品文档)
- [ ] 所有 API 接口文档(用 FastAPI 自动生成的 `/docs` 即可)
- [ ] 至少 5 个完整的端到端测试 case
- [ ] 团队分工与贡献说明

---

## 附录 A:推荐的目录初始化命令

```bash
# 项目根目录
mkdir -p local-route-agent && cd local-route-agent
git init

# 后端
mkdir -p backend/app/{api,models,schemas,services,repositories,llm/prompts,solver,utils}
mkdir -p backend/tests backend/alembic
touch backend/pyproject.toml backend/README.md

# 前端
mkdir -p frontend/src/{pages,components/ui,hooks,store,api,types,styles}
mkdir -p frontend/public
touch frontend/package.json frontend/README.md

# 数据与脚本
mkdir -p data/{raw,processed,chroma}
mkdir -p scripts docs

# 根目录文件
touch docker-compose.yml .env.example .gitignore README.md
```

## 附录 B:推荐的 Prompt 模板示例

`app/llm/prompts/intent.py` 示例:

```python
INTENT_PROMPT = """你是一个本地出行规划助手的意图理解模块。
请将用户的需求解析为结构化的规划任务。

# 用户信息
- 城市: {city}
- 日期: {date}
- 时间窗: {start_time} - {end_time}
- 同行人: {party}
- 预算: 人均 {budget} 元
- Persona 标签: {persona_tags}

# 用户已勾选的 POI
{selected_pois}

# 用户的自由补充
{free_text}

# 输出要求
严格按以下 JSON Schema 输出,不要有任何额外文字:
{{
  "hard_constraints": {{
    "start_time": "HH:MM",
    "end_time": "HH:MM",
    "budget_total": <int 或 null>,
    "transport_mode": "walking" | "driving" | "transit" | "mixed",
    "must_include_meal": true | false
  }},
  "soft_preferences": {{
    "pace": "efficient" | "relaxed" | "balanced",
    "avoid_queue": true | false,
    "weather_sensitive": true | false,
    "photography_priority": true | false,
    "food_diversity": true | false,
    "custom_notes": ["...", "..."]
  }},
  "must_visit_pois": [<poi_id>...],
  "avoid_pois": [<poi_id>...]
}}

# 推理要点
- 如果用户说"不想赶",pace 应为 "relaxed"
- 如果同行人是 "couple",photography_priority 倾向 true
- 如果时间窗 < 4 小时,must_include_meal 倾向 false
- custom_notes 收集所有未被结构化字段覆盖的偏好
"""
```

---

**文档结束**

> 本文档版本:v1.0 / 实施周期:4 周 / 适用团队规模:3-4 人
>
> 任何对数据 schema、模块接口的修改必须更新本文档并通知所有开发成员。

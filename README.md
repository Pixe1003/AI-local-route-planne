# AIroute · 合肥本地生活路线 Agent Demo

AIroute 是一个面向本地居民空闲出行的智能体 Demo。用户输入空闲时间、预算、出发点、天气和偏好后，系统结合历史偏好、演示 UGC、POI 结构化信息、距离、排队、天气和预算约束，生成可解释、可调整、可降级的合肥本地游玩/餐饮路线。

当前版本聚焦 **合肥 Demo**，不做登录、下单、优惠券、支付和商家转化。项目重点是把“智能体推荐路线”做成可迁移的工程系统：候选召回、路线求解、业务约束、多样性、地图降级和离线评测都有明确边界。

[业务 Demo 评测](docs/business-demo-eval.md) · [当前架构](docs/current-architecture.md) · [技术复盘](docs/AIroute-技术复盘-面试深挖版.md) · [改造方案](docs/AIroute-改造方案.md) · [响应延迟优化](docs/响应延迟优化与待补数据.md) · [技术评审总结](docs/项目总结-技术评审版.md)

---

## 项目解决什么问题

典型用户不是游客，而是合肥本地居民：

> “今天下午有空，想少排队，吃点本地菜，顺路逛逛/拍照，预算别太高。”

传统搜索或榜单会给出离散 POI，用户还要自己判断距离、排队、天气、预算和路线顺序。AIroute 的目标是把这类自然语言需求变成一组可执行方案：

- 推荐 3-5 个 POI 的路线，而不是单点榜单。
- 餐饮、景点、文化、购物、娱乐、咖啡等 POI 穿插安排，避免一路堆餐厅。
- 给出多个 Pareto 方案，例如“兴趣优先 / 少排队 / 省预算 / 短通勤 / 室内稳妥”。
- 点击不同方案后，地图、站点、耗时、距离和理由同步切换。
- 高德地图不可用时，仍返回文字路线和估算通勤，不让 Agent 整体失败。
- 用户继续对话提出“换近一点的餐厅”“不要排队”“预算再低点”后，系统能基于原计划调整。

---

## 当前 Demo 范围

| 项 | 当前状态 |
| --- | --- |
| 城市 | 只开放合肥，前后端不暗示多城市能力 |
| 日期 | 前端默认当天；后端 schema 保留日期字段 |
| UGC | 使用 deterministic 脚本生成演示 UGC，来源统一为 `simulated_ugc` |
| 天气 | 前端手动选择 `normal / rainy / hot / cold`，暂不接天气 API |
| 地图 | 正常走高德 Web Service；缺 key 或失败时降级为文字路线 |
| 登录 | 暂不做登录系统，使用 demo/user_id 级别偏好和会话记忆 |
| 商业闭环 | 暂不做下单、支付、优惠券、商家转化 |
| 数据迁移 | Demo 数据留在 SQLite / JSONL / FAISS，本阶段不做生产数据库迁移 |

---

## 核心链路

```mermaid
flowchart LR
  U["用户自然语言\n预算/时间/天气/偏好"] --> UI["React Demo UI\n合肥 + 当天日期 + 天气选择"]
  UI --> A["POST /api/agent/run"]
  A --> INTENT["parse_intent\n意图与硬约束识别"]
  INTENT --> POOL["recommend_pool\n结构化召回 + 单次 FAISS 语义补充"]
  POOL --> SCORE["POI scoring\n天气/预算/排队/距离/UGC"]
  SCORE --> SOLVE["solve_constrained_route\nOPTW + CP-SAT + Pareto"]
  SOLVE --> MIX["路线节奏守卫\n餐饮<=2 + 品类穿插 + 多样性"]
  MIX --> STORY["compose_story\n理由与取舍说明"]
  STORY --> AMAP["get_amap_chain\n高德路线或文字降级"]
  AMAP --> VALID["validate_route + robustness\n合法性与准时概率"]
  VALID --> PAGE["AmapRoutePage\n方案卡 + 地图/文字路线 + 继续对话"]
```

Agent 不直接“编造路线 JSON”。它主要负责决策和编排：什么时候解析意图、什么时候召回、什么时候求解、什么时候降级。路线本身由结构化召回、打分、约束求解和校验共同决定。

---

## 推荐逻辑

### 约束分层

| 层级 | 示例 | 处理方式 |
| --- | --- | --- |
| 硬约束 | 合肥范围、必去/避开 POI、营业关闭、至少 3 个 POI、时间窗不可超出 | 不满足则路线无效或触发修复 |
| 业务护栏 | 预算、排队、天气、距离 | 默认做惩罚和风险提示；用户说“严格预算/绝不排队/必须室内”时升级为硬约束 |
| 软偏好 | 本地菜、拍照、咖啡、文化、商场、慢节奏、少通勤 | 进入 scoring 和解释，不直接让路线无效 |

`constraint_satisfaction_rate=1.0` 只说明路线合法，不代表路线足够丰富。因此评测额外检查方案重叠度、品类熵、商圈分散度、业务预期通过率等指标。

### 召回与性能

- 普通请求：结构化候选 + 一次 FAISS 语义检索，`poi_profile` 和 `ugc_review` 合并查询。
- 预算优先场景（低预算/控预算请求）：结构化候选优先；候选充足时跳过语义检索，避免 30s+ 冷启动阻塞。
- 语义检索有超时和冷却期：超时、异常、无 FAISS、冷却期内都降级为结构化候选。
- `PoolService.last_retrieval_stats` 会记录 `retrieval_mode / semantic_status / semantic_query_count / semantic_elapsed_ms` 便于诊断。

### 路线节奏

- 餐饮类 POI 默认不超过 2 个。
- 正常路线按“餐饮 + 1-2 个非餐饮 + 第二餐饮”或“非餐饮 + 餐饮 + 非餐饮 + 餐饮”组织。
- 两个餐饮点尽量避免同品类，例如不连续给两个快餐。
- 咖啡作为轻休闲点处理，不计入正式餐饮上限。
- 雨天/炎热天气优先室内文化、商场、咖啡、娱乐和短通勤。

### Pareto 方案

每个方案包含：

- `ordered_ids`：该方案自己的 POI 顺序。
- `business_label`：业务标签，如“少排队”“省预算”“室内稳妥”。
- `diversity_score`：与其它方案的差异度。
- `tradeoff_reason`：为什么这个方案值得保留。

方案过滤会控制 POI Jaccard overlap，默认目标不高于 `0.6`；候选不足时放宽到 `0.8` 并在前端提示“候选受限，方案差异较小”。

---

## 最新评测表现

最新扩展评测报告见 [data/eval/route_eval_expanded_scenarios.md](data/eval/route_eval_expanded_scenarios.md)。当前 10 个场景覆盖低预算、雨天室内、少排队、必去点、餐饮穿插、炎热室内、拍照咖啡文化、亲子短路线和晚间购物晚餐。

| 指标 | 最新值 | 说明 |
| --- | ---: | --- |
| 场景数量 | 10 | 合肥 Demo 业务场景 |
| 可行率 | 1.0 | 每个场景都有可返回路线 |
| 约束满足率 | 1.0 | 硬约束合法性 |
| 解释忠实度 | 1.0 | 理由能对齐 POI 属性/UGC evidence |
| 平均耗时 | ~5.9s | 主要剩余耗时在 `compose_story` |
| 平均方案数 | 5 | 每场景 5 个 Pareto 方案 |
| 平均方案重叠度 | 0.465 | 越低代表方案差异越大 |
| 平均品类熵 | 1.006 | 用于检查是否过度模板化 |
| 业务预期通过率 | 0.8 | 暴露地理紧凑性和雨天亲子品类丰富度仍可优化 |

已知仍需优化的业务问题：

- 个别餐饮穿插路线的直线段距离偏长，地理紧凑性还需要更强的替换/惩罚策略。
- 雨天亲子短路线可行但品类熵偏低，室内候选还需要更均衡覆盖文化/商场/咖啡/娱乐。

---

## 快速启动

### 1. 安装依赖

```powershell
cd <repo-root>

python -m venv .venv
.\.venv\Scripts\Activate.ps1

cd backend
pip install -e .[dev]
cd ..

cd frontend
npm install
cd ..
```

### 2. 准备 Demo 数据

```powershell
# 导入合肥 POI SQLite
python scripts\import_hefei_pois.py

# 生成演示 UGC，不抓取外部平台
python scripts\generate_demo_ugc.py

# 构建 FAISS RAG 索引
$env:AIROUTE_REAL_DATA_DIR = Join-Path (Get-Location) 'data\processed'
python scripts\build_faiss_rag.py --city hefei --sqlite-path "$env:AIROUTE_REAL_DATA_DIR\hefei_pois.sqlite" --require-real-data --index-dir data\faiss

# 可选：把 UGC evidence 写入 SQLite 派生索引
python scripts\build_retrieval_index.py

# 可选：训练 LambdaMART ranker
python scripts\train_ranker.py
```

### 3. 启动服务

```powershell
# 后端
python -m uvicorn app.main:app --app-dir backend --reload --port 8000

# 前端
cd frontend
npm run dev
```

打开 `http://127.0.0.1:5173`。首页会默认合肥和当天日期，支持天气选择、预算输入、出发点和自然语言偏好。

### 4. 运行评测

```powershell
# 后端测试
cd backend
pytest -q

# 扩展业务评测
python -m eval.run_eval --out ..\data\eval\route_eval_expanded_scenarios.md --enforce-gate

# 前端测试
cd ..\frontend
npm test
```

---

## 配置项

```powershell
# LLM：OpenAI 兼容接口，支持 LongCat / DeepSeek 等
LLM_PROVIDER=longcat
LLM_BASE_URL=https://api.longcat.ai/v1
LLM_MODEL=longcat-max
LLM_API_KEY=your_llm_key
AGENT_TOOL_CALLING_ENABLED=true
AGENT_FAST_DECISION_ENABLED=true

# 高德地图：缺失时 Agent 自动走文字路线降级
AMAP_WEB_SERVICE_KEY=your_amap_web_service_key
AMAP_KEY=optional_fallback_amap_key

# RAG / FAISS
FAISS_INDEX_PATH=data/faiss
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
SEMANTIC_RETRIEVAL_TIMEOUT_MS=1200
BUDGET_FIRST_SEMANTIC_TIMEOUT_MS=600
BUDGET_FIRST_THRESHOLD=100
SEMANTIC_TIMEOUT_COOLDOWN_SECONDS=60

# Ranker
RANKER_ENABLED=true
RANKER_MODEL_PATH=data/models/ranker.txt

# 前端
VITE_API_BASE_URL=http://127.0.0.1:8000/api
VITE_AMAP_JS_KEY=your_amap_js_key
VITE_AMAP_SECURITY_JS_CODE=your_amap_security_js_code
```

---

## 核心接口

| 接口 | 用途 |
| --- | --- |
| `POST /api/agent/run` | 起一次完整路线规划 |
| `POST /api/agent/adjust` | 基于用户反馈调整既有计划 |
| `GET /api/agent/trace/{session_id}` | 查看 Agent 工具调用轨迹 |
| `GET /api/agent/stream/{session_id}` | SSE 订阅 Agent 思考过程 |
| `POST /api/pool/generate` | 生成候选池 |
| `POST /api/route/chain` | 高德实路网路线链 |
| `GET /api/ugc/feed` | 演示 UGC 发现流 |
| `GET /health` | 健康检查：RAG / FAISS / Amap 状态 |
| `GET /metrics` | Prometheus 指标 |

---

## 项目结构

```text
AIroute/
├── backend/
│   ├── app/
│   │   ├── agent/           Conductor、tools、story/repair specialists
│   │   ├── api/             FastAPI 路由
│   │   ├── services/        pool、scoring、retrieval、plan、amap、validator
│   │   ├── solver/          OPTW、Pareto、distance、route compaction
│   │   ├── repositories/    SQLite POI、FAISS、session vector、Amap cache
│   │   ├── ml/              LambdaMART ranker
│   │   └── observability/   logging、metrics、tracing
│   ├── eval/                10 个场景 YAML、metrics、run_eval
│   └── tests/               后端单测、业务 Demo readiness、snapshot
├── frontend/
│   └── src/
│       ├── pages/           AmapRoutePage、DiscoveryFeedPage、ProjectReviewPage
│       ├── components/      地图与路线组件
│       └── __tests__/       Vitest 前端测试
├── scripts/                 数据导入、UGC 生成、FAISS 构建、ranker、bench
├── data/                    processed、faiss、models、eval 报告
└── docs/                    详细设计、评测、复盘和历史方案
```

---

## 文档索引

| 文档 | 作用 |
| --- | --- |
| [业务 Demo 评测](docs/business-demo-eval.md) | 业务验收场景、指标、约束分层和手动验收步骤 |
| [当前架构](docs/current-architecture.md) | 当前主链路、后端模块、召回/路线/前端边界 |
| [技术复盘：面试深挖版](docs/AIroute-技术复盘-面试深挖版.md) | 技术亮点、取舍、可讲述的工程细节 |
| [AIroute 改造方案](docs/AIroute-改造方案.md) | 早期复杂度升级与工程化改造方案 |
| [响应延迟优化与待补数据](docs/响应延迟优化与待补数据.md) | 性能优化记录、延迟组成和后续优化方向 |
| [项目总结：技术评审版](docs/项目总结-技术评审版.md) | 黑客松/评审视角的完整总结 |
| [简历项目经历](docs/简历项目经历.md) | 简历和面试材料 |

---

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python、FastAPI、Pydantic v2、SQLite、structlog、Prometheus |
| Agent | OpenAI 兼容 function calling、规则 fallback、tool whitelist |
| 召回 | SQLite/FTS、FAISS、sentence-transformers、BGE small zh |
| 排序 | 规则分、LightGBM LambdaMART |
| 路线 | OR-Tools CP-SAT、OPTW、Pareto、多样性过滤 |
| 地图 | 高德 Web Service API、缺 key 文字路线降级 |
| 前端 | React、Vite、TypeScript、Zustand、Vitest |

---

## 一句话总结

AIroute 不是让 LLM 直接编路线，而是把 LLM 放在编排层，把路线可行性、多样性、业务护栏和降级能力放进确定性的工程链路里。

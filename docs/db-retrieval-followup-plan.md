# AIroute 数据库与检索策略 — 后续修改计划

> 本文基于一次围绕「数据库更新 + 检索策略更新」的代码评审，整理出分阶段的可执行改造计划。
> 每条任务标注：**问题现状 / 涉及文件 / 建议改法 / 验收标准**。
> 优先级：**P0 阻断级 → P1 检索质量 → P2 路线质量 → P3 工程与文档**。
>
> 待验证项（本次评审时沙箱不可用，未能跑 SQL）：真实 `hefei_pois` 的行数、类目分布、Chroma 索引是否已构建、embedding key 是否配置。下方相关任务以「待验证」标记，请先确认再动手。

---

## 一、现状速览

**已完成且质量较好：**

- 数据库由单表升级为 `app_pois` 视图 + `poi_feature_index` + `ugc_evidence_index` 三结构，字段映射、类目归一化、按类目配额召回都已实现。
- 检索升级为真实 RAG：`ChromaVectorIndex`（cosine/HNSW），POI 资料文档（poi_profile）与 UGC 评论文档（ugc_review）分 source_type 建库；`pool_service` 三通道召回（语义 profile + 语义 ugc + feature_bucket）并按最高分去重合并。
- 证据与来源链（`retrieval_score / provenance / evidence_snippets`）一路透传到候选池、路线站点、备选 POI，可追溯解释做得扎实。
- 分层降级干净，RAG 相关测试覆盖到位。

**主要不足（本计划要解决的）：**

- 数据与检索一致性问题：DB 文件名带空格、城市错配静默兜底、RAG 可能未真正启用、距离完全未进入召回与评分。
- 检索召回质量：本地兜底关键词词表窄、类目后过滤可能凑不够数、embedding 无缓存/无 rerank。
- 路线质量：求解器仅 greedy+最近邻、营业时间校验形同虚设、partial replan 无"已完成站点"概念。
- 工程与文档：文档与代码漂移、缺真实 DB 冒烟测试、意图/重规划纯关键词规则。

---

## 二、P0 — 阻断级：数据与检索一致性

> 这一阶段直接决定「检索策略更新」是真生效还是只停在代码里，建议最先做。

### P0-1 修复 DB 文件名带空格的隐患

- **问题**：实际文件名为 `hefei_pois .sqlite`（扩展名前有空格），`poi_repo.py` 用 `with_name("hefei_pois .sqlite")` 兜底，脆弱且会传染到其他工具脚本。
- **涉及文件**：`data/processed/hefei_pois .sqlite`、`backend/app/repositories/poi_repo.py`（`_default_sqlite_path`）、`backend/app/config.py`（`poi_sqlite_path`）。
- **改法**：
  1. 重命名文件为 `hefei_pois.sqlite`（无空格）。
  2. 删除 `poi_repo.py` 中所有 `"hefei_pois .sqlite"` 的空格兼容分支。
  3. 确认 `config.poi_sqlite_path` 指向新名字。
- **验收**：全代码搜索不再出现带空格文件名；`PoiRepository().list_by_city("hefei")` 正常返回。

### P0-2 消除「城市错配」静默兜底

- **问题**：seed 数据是上海，主城市是合肥。合肥 DB 读不到时，`pool_service` 与 `solver` 会在 `city="hefei"` 时静默回退到上海 POI，给合肥用户返回上海地点。
- **涉及文件**：`backend/app/services/pool_service.py`（`_candidate_pois` 里 `if not city_pois and city != "shanghai"`）、`backend/app/services/solver_service.py`（`_ensure_minimum_candidates` 的 `or self.repo.list_by_city("shanghai")`）。
- **改法**：
  1. 去掉跨城市的隐式回退；当目标城市候选为空时，返回明确的空结果 + 结构化告警，而不是换城市。
  2. 若仍需 seed 兜底，必须按 `city` 过滤 seed，且只在 seed 含该城市数据时启用。
- **验收**：当合肥 DB 缺失时，接口不再返回上海 POI；返回体或日志能看到"该城市无候选/数据源缺失"的明确信号。

### P0-3 确认并暴露 RAG 是否真正启用（待验证）

- **问题**：`RetrievalService._default_vector_index` 要求 `rag_enabled and embedding_api_key` 才启用语义检索；仓库未见 `data/chroma` 索引目录。若未配 key / 未 build index，则语义召回整条失效，实际只剩 `feature_bucket` 关键词匹配，demo 跑的是降级链路。
- **涉及文件**：`backend/app/config.py`、`backend/app/services/retrieval_service.py`、`backend/app/repositories/rag_index.py`、`backend/app/main.py`（`/health`）。
- **改法**：
  1. 确认 `.env` 中 `EMBEDDING_API_KEY`、`EMBEDDING_BASE_URL`、`RAG_ENABLED` 配置。
  2. 执行 `python -m app.repositories.rag_index build --city hefei --source data/processed/hefei_pois.sqlite --reset` 并确认 `data/chroma` 生成、文档数 > 0。
  3. 在 `/health`（或新增 `/api/meta/rag-status`）返回：rag_enabled、index 是否存在、collection 文档数、embedding 是否可用——让"是否在用真实 RAG"可观测。
- **验收**：健康检查能明确显示 RAG 生效状态；本地构建索引后，`RetrievalService.retrieve` 返回非空且 `provenance` 含 `semantic_*`。

### P0-4 把「距离/就近」纳入召回与评分

- **问题**：`distance_penalty` 在 `poi_scoring_service` 中硬编码为 `0.0`；`amap_key` 配置了但全代码从未使用；距离只在 `distance.py` 用 haversine×1.3 直线估算。即时本地场景核心是"顺路就近"，但召回和打分都不看出发点距离。
- **涉及文件**：`backend/app/services/poi_scoring_service.py`、`backend/app/services/pool_service.py`、`backend/app/services/retrieval_service.py`、`backend/app/solver/distance.py`、`backend/app/schemas/*`（可能需新增 origin 字段）。
- **改法**：
  1. 在请求上下文里引入出发点/出发区域坐标（profile 已有"出发区域"，需落到经纬度）。
  2. 在 `RetrievalQuery` 与召回后置过滤中加入距离上限（半径过滤），优先就近。
  3. 实现 `_distance_penalty`：按到出发点（或上一站）的距离给负分，替换当前的 `0.0`。
  4. （可选，后续）接入高德 `amap_key` 做真实距离/时长，保留 haversine 作为降级。
- **验收**：同等评分下更近的 POI 排序更靠前；新增评分项单测覆盖"远 POI 被扣分""半径外 POI 不召回"。

---

## 三、P1 — 检索召回质量

### P1-1 扩展本地语义兜底，弱化硬编码词表

- **问题**：`VectorRepository.score` 与 `feature_bucket` 命中靠硬编码小词表（拍照/咖啡/排队…），中文无分词，覆盖窄，且降级时是唯一语义来源。
- **涉及文件**：`backend/app/repositories/vector_repo.py`、`backend/app/services/pool_service.py`（`_feature_bucket_candidates`）。
- **改法**：引入轻量中文分词/同义词归并（或基于 `high_freq_keywords` + tags 的 token 命中），把固定词表改为可配置词典 + 标签权重。
- **验收**：构造若干口语 query（如"带老人散步""下雨天室内"），降级链路下召回命中率明显提升，有对比单测。

### P1-2 类目过滤改为检索前置/补偿

- **问题**：`ChromaVectorIndex.query` 的 `category_filters` 在向量检索后做后过滤，类目过滤后可能凑不够 `top_k`。
- **涉及文件**：`backend/app/repositories/vector_repo.py`（`query`、`_query_where`）。
- **改法**：把 category 放进 Chroma `where`（metadata 已有 `category`），或在后过滤不足时自动放大 `n_results` 再补召回。
- **验收**：带 category_filters 的查询稳定返回 `top_k` 条（数据足够时），单测覆盖。

### P1-3 embedding 查询缓存与可选 rerank

- **问题**：embedding 无 `embed_query`/缓存/批量去重，每次查询都打 API；无 rerank，直接用 cosine 距离。
- **涉及文件**：`backend/app/llm/embedding.py`、`backend/app/repositories/vector_repo.py`。
- **改法**：加查询级缓存（LRU）；可选接入 rerank（交叉编码或规则重排，结合 rating/queue/距离）。
- **验收**：相同 query 二次调用不再打 embedding API；重排后 Top 结果与业务约束（低排队/就近）更一致。

---

## 四、P2 — 路线质量（POI 质量 ≠ 路线质量）

### P2-1 求解器从 greedy 升级为约束化行程优化

- **问题**：`solver_service` 本质是 greedy 排序 + 最近邻排序，未真正优化顺序连贯性、节奏、疲劳（SKILL 要求 beam/insertion/local search）。
- **涉及文件**：`backend/app/services/solver_service.py`、`backend/app/solver/`。
- **改法**：先上 insertion 启发式 + 2-opt 局部搜索，目标函数纳入旅行时间、步行距离、排队总时长、时间节奏；候选量大时再考虑 beam search。
- **验收**：相同候选集下，新求解器的总步行距离/总旅行时间不劣于旧版，且有路线级指标的对比测试。

### P2-2 让营业时间校验真正生效

- **问题**：`_is_open` 在 `open_hours` 为空时返回 True，而真实 DB 的 `open_hours_json` 多为 `{}`，导致这条硬约束形同虚设。
- **涉及文件**：`backend/app/services/route_validator.py`、数据侧 `open_hours_json` 填充（ETL/建库脚本）。
- **改法**：补全 DB 的营业时间数据；缺失时给出"营业时间未知"的 warning（而非静默放行），高风险时段提示用户到店前确认。
- **验收**：有营业时间的 POI 在闭店时段会被标记 `poi_closed`；缺失数据时产生 warning 而非 error。

### P2-3 partial replan 引入「已完成站点/当前位置」

- **问题**：`route_replanner._compress_route` 只从末尾 `pop`，没有 SKILL 定义的"保留已完成站点、只重排剩余"。
- **涉及文件**：`backend/app/services/route_replanner.py`、`backend/app/schemas/chat.py`（可能需 current_stop_index）。
- **改法**：请求带"当前所在站点/已完成站点"，partial replan 只对剩余站点重排/裁剪。
- **验收**：传入已完成前 N 站后，replan 结果保留前 N 站不变，仅调整其后站点，有单测。

---

## 五、P3 — 工程与文档

### P3-1 同步文档与代码

- **问题**：`docs/current-architecture.md` 引用了已不存在的文件（`poi_repository.py`、`validator.py`、`routes_replan.py`、`TripsPage.tsx`）；`backend/README` 写"上海"、根 README 写"合肥"；SKILL First Read 也列着已删的 `routes_replan.py`。
- **涉及文件**：`docs/current-architecture.md`、`backend/README.md`、`README.md`、`skills/local-route-agent/SKILL.md`。
- **改法**：按当前真实文件树更新架构图与文件清单，统一城市口径为合肥（上海为 seed 兜底说明）。
- **验收**：文档中所有文件路径均真实存在；城市描述一致。

### P3-2 补真实 DB 冒烟测试

- **问题**：现有测试都用 tmp 内联建库，真实 `hefei_pois.sqlite` 的行数、类目分布、index 完整性无任何断言。
- **涉及文件**：`backend/tests/`（新增 `test_real_sqlite_smoke.py`）。
- **改法**：新增针对真实文件的冒烟测试：文件存在、`app_pois` 行数 > 阈值、每个 canonical 类目均有数据、`poi_feature_index` 与 `ugc_evidence_index` 非空（文件缺失时 skip）。
- **验收**：CI/本地能快速发现真实数据缺类目或表为空。

### P3-3 明确「多风格路线」产品定位

- **问题**：后端 `PlanResponse` 仍返回 3 条 style 路线、前端 `planStore` 保留全部并支持 `switchPlan`，但架构文档说已收敛为"单条主路线"。
- **涉及文件**：`backend/app/services/plan_service.py`、`frontend/src/store/planStore.ts`、`docs/current-architecture.md`。
- **改法**：确认产品是否保留多风格对比；保留则更新文档，收敛则精简后端只产出主路线 + 备选。
- **验收**：代码行为与文档一致。

### P3-4 意图/重规划从纯关键词向 LLM+规则演进（可选）

- **问题**：`intent_service`、`chat_service._detect_intent` 纯关键词规则；SKILL 列出的"亲子友好/老人友好"等 replan 控件未实现。
- **涉及文件**：`backend/app/services/intent_service.py`、`backend/app/services/chat_service.py`、`backend/app/services/route_replanner.py`。
- **改法**：补齐 SKILL 列出的 replan 控件（亲子/老人友好、少走路等）；关键词作为 LLM 不可用时的兜底。
- **验收**：常见调整指令均能正确分类并触发对应 replan，含单测。

---

## 六、建议落地顺序

1. **先做 P0-3 + P0-1 + P0-2**：确认 RAG 是否真在跑、修文件名、去掉城市错配兜底——这决定检索更新是否真正生效。
2. **再做 P0-4**：把距离/就近接入召回与评分——本地即时场景的核心体验。
3. **然后 P1 检索质量** 与 **P3-1/P3-2 文档与冒烟测试**（成本低、收益稳）。
4. **最后 P2 路线质量**：求解器与校验升级，按时间预算推进。

## 七、整体验收口径

- 真实合肥 DB 下，候选池/路线/备选均带 `semantic_*` provenance（证明 RAG 生效）。
- 不再出现跨城市错配的 POI。
- 评分与召回对"距离/就近"敏感。
- 关键链路（召回、评分、求解、校验、重规划）单测齐全且通过，新增真实 DB 冒烟测试。
- 文档与代码、城市口径一致。

# AIroute 统一重构方案（FAISS 检索 + 全能力合并，功能不缺失）

> 目标：从 `main` 切新分支统一重构，向量检索引擎采用 **FAISS**，把两条分支的能力合并到一条主干，**保证功能不缺失**。
>
> 两条来源分支：
> - `codex/real-rag-upgrade`（当前分支）：干净的**双通道检索**（poi_profile / ugc_review）、证据聚合、`provenance`、三表 SQLite、类目归一化、`feature_bucket` 兜底、分层降级、RAG 测试。引擎是 Chroma。
> - `codex/longcat-api`：**FAISS UGC RAG** + 生成索引、**agent memory**、**observability**、**cache**、**quality gates**、**高德(Amap)路由**。未并入 main。
>
> 决策：引擎统一为 **FAISS**；检索的**设计**（双通道 + 证据 + provenance + 降级）取自 real-rag-upgrade，但底层换成 FAISS 实现。
>
> ⚠️ 重要前提：本方案撰写时无法运行 git，`longcat-api` 的具体实现细节是从提交信息推断。**Phase 0 的逐文件能力盘点是强制第一步**，必须先用 git 把两条分支的真实实现盘清楚，再开始迁移。

---

## 0. 设计原则（贯穿全程）

- **能力不丢**：任何一条分支已实现的能力，在新主干上必须有等价或更优实现，并有测试为证。
- **契约稳定**：`RetrievalService / RetrievalQuery / RetrievedPoi / EvidenceSnippet` 这套检索契约保持不变，引擎（FAISS）只是其后端实现 → 换引擎不影响上层服务。
- **增量可验证**：每个 Phase 自成闭环、独立可测、可单独回滚；旧分支保留为对照基线，不删除。
- **降级优先**：FAISS/embedding/高德/记忆任一不可用，主链路都能用确定性兜底完成 demo。

---

## 1. 目标架构

```text
backend/app
  api/                      FastAPI 路由（保持现有端点）
  services/
    retrieval_service.py    引擎无关的检索编排（双通道召回 + 证据聚合 + provenance）
    pool_service.py         多通道召回 + 评分 + 多样性选择
    plan_service.py         规划编排 + 备选
    solver_service.py       行程求解
    route_validator.py      约束校验
    route_repairer.py       有界修复
    route_replanner.py      事件重规划
    memory_service.py       【并回】agent memory / 会话偏好
    observability.py        【并回】结构化日志 / trace / metrics
    cache_service.py        【并回】embedding & 检索结果缓存
  repositories/
    sqlite_poi_repo.py      三表 SQLite（app_pois 视图 + poi_feature_index + ugc_evidence_index）
    poi_repo.py             POI 访问 + seed 兜底
    faiss_index.py          【新】FaissVectorIndex（替代 ChromaVectorIndex）
    faiss_meta.py           【新】FAISS 向量 id ↔ 元数据 sidecar（city/category/source_type/doc_id）
    rag_build.py            【整合】索引构建脚本（双 source_type 文档 → FAISS）
  routing/
    amap_client.py          【并回】高德距离/时长，haversine 作降级
  llm/
    embedding.py            embedding 客户端（接缓存）
    client.py               LLM JSON 边界
  schemas/                  rag.py / plan.py / pool.py / poi.py 等
data/
  processed/                hefei_pois.sqlite（修掉文件名空格）、ugc_*.jsonl
  faiss/                    【新】FAISS 索引 + meta sidecar 落盘目录
```

关键点：**`RetrievalService` 已经是引擎无关的**（它只调用 `vector_index.query(...)`）。所以"Chroma → FAISS"只需新增一个与 `ChromaVectorIndex.query` 同签名的 `FaissVectorIndex`，上层完全不改。

---

## 2. 能力清单（"功能不缺失"的基准矩阵）

> 这是验收基准。每一行在新主干上都必须有"目标实现 + 验证方式"。`longcat-api` 列标注"待盘点"的，需 Phase 0 用 git 确认后补全实现细节。

| 能力 | 来源 | 现状 | 新主干目标实现 | 验证方式 |
|---|---|---|---|---|
| 三表 SQLite（app_pois 视图 + poi_feature_index + ugc_evidence_index） | real-rag-upgrade | 已有 | 原样保留 | 真实 DB 冒烟测试 |
| 类目归一化（derived_category + 关键词启发式） | real-rag-upgrade | 已有 | 原样保留 | 现有单测 |
| 双通道文档（poi_profile / ugc_review） | real-rag-upgrade | 已有 | 保留，写入 FAISS | 索引构建后两类文档数 > 0 |
| 多通道召回 + 证据聚合 + provenance | real-rag-upgrade | 已有 | 保留，后端换 FAISS | provenance 含 semantic_* |
| feature_bucket 关键词兜底 | real-rag-upgrade | 已有 | 保留 | 降级单测 |
| 分层降级（无 key/无索引不崩） | real-rag-upgrade | 已有 | 保留 | 降级单测 |
| 向量引擎 | 两者 | Chroma / FAISS | **统一 FAISS** + meta sidecar | 检索单测对齐 |
| FAISS 索引与生成脚本 | longcat-api | 待盘点 | 整合进 rag_build，支持双 source_type | 索引文件生成 |
| 高德(Amap)路由距离/时长 | longcat-api | 待盘点 | routing/amap_client + 接入 solver/评分 | 真实/降级双路径单测 |
| distance_penalty 真正生效 | 缺（恒 0） | — | 评分接入距离 | 远 POI 被扣分单测 |
| agent memory / 会话偏好 | longcat-api | 待盘点 | memory_service + agent_sessions.sqlite | 记忆读写单测 |
| 缓存（embedding/检索） | longcat-api | 待盘点 | cache_service（LRU/落盘） | 二次查询不打 API |
| observability（日志/trace/metrics） | longcat-api | 待盘点 | observability + /health 暴露状态 | /health 显示各子系统状态 |
| quality gates | longcat-api | 待盘点 | 整合进 CI/校验 | 门禁脚本通过 |
| 三风格求解 + 校验 + 修复 + 重规划 | 两者 | 已有 | 保留 | 现有单测 + runner |

---

## 3. 分阶段实施

### Phase 0 — 建基线与能力盘点（强制先做）

1. 从 main 切新分支：`git checkout main && git checkout -b codex/unified-refactor`。
2. 逐分支盘点（产出"文件级能力映射表"）：
   - `git log --oneline main..codex/longcat-api`、`git diff main...codex/longcat-api --stat`
   - `git diff main...codex/real-rag-upgrade --stat`
   - 重点读出 longcat-api 的：FAISS 索引/查询、记忆模块、缓存、observability、高德客户端各自的文件、入口、配置项。
3. 把第 2 节矩阵里"待盘点"的行补成真实文件路径与函数签名。
4. 落地 **功能不缺失检查表**（见第 4 节），作为后续每个 Phase 的验收。
- **退出标准**：矩阵无"待盘点"、新分支建好、检查表成文。

### Phase 1 — 数据与索引底座

1. 修复 DB 文件名：`hefei_pois .sqlite` → `hefei_pois.sqlite`，删 `poi_repo.py` 的空格兜底，校正 `config.poi_sqlite_path`。
2. 保留三表 SQLite 结构与 `sqlite_poi_repo` 的字段映射、类目归一化。
3. 新增 `repositories/faiss_index.py` + `faiss_meta.py`：
   - 文档构造沿用 real-rag-upgrade 的 `build_poi_document` / `build_ugc_documents`（双 source_type）。
   - 因 **FAISS 无元数据过滤**：用 sidecar（sqlite/parquet/json）维护 `faiss_id → {poi_id, doc_id, city, category, source_type}`；查询时先 ANN 取 `top_k * N`，再按 sidecar 做 city/source_type/category 过滤补齐。
   - 可选按 city 分库或按 source_type 分库以提升过滤效率。
4. `rag_build.py`：合并 longcat-api 的 FAISS 生成脚本与 real-rag-upgrade 的双文档逻辑，落盘到 `data/faiss/`。
- **退出标准**：能用真实合肥 DB 构建出含 poi_profile + ugc_review 两类文档的 FAISS 索引；sidecar 元数据完整。

### Phase 2 — 检索层（引擎=FAISS，设计=双通道+provenance）

1. `FaissVectorIndex.query(*, text, city, top_k, category_filters=None, source_types=None)`：与 `ChromaVectorIndex.query` **完全同签名**，返回同结构 rows（poi_id/score/doc_id/source_type/text/metadata）。
2. `RetrievalService` 与 `pool_service` 多通道召回、`_merge_retrieved`、证据聚合、`provenance`、`feature_bucket` 兜底**全部保留不改**。
3. `RetrievalService._default_vector_index` 改为构建 `FaissVectorIndex`；保留"无 embedding key / 索引缺失 → 返回空"的降级。
4. embedding 查询接 `cache_service`（见 Phase 4）。
- **退出标准**：把现有两份 RAG 测试（`test_real_rag_upgrade`、`test_multitype_rag_recall`）的 FakeVectorIndex 替换/补充为 FAISS 路径，断言 provenance、证据聚合、降级与原来一致。

### Phase 3 — 路由 / 距离（高德接回 + 距离进评分）

1. `routing/amap_client.py`：从 longcat-api 移植高德客户端（key 取 `config.amap_key`）。
2. `solver/distance.py` 的 `estimate_transport` 优先用高德距离/时长，**haversine 作降级**。
3. 评分接入距离：实现 `poi_scoring_service._distance_penalty`，替换当前恒 `0.0`；召回阶段加半径/就近过滤（需出发点坐标，profile 的"出发区域"落到经纬度）。
- **退出标准**：高德可用/不可用双路径单测；"更近的 POI 排序更靠前""半径外不召回"单测。

### Phase 4 — 记忆 / 缓存 / 可观测 / 质量门

1. `memory_service.py`：移植 longcat-api 的 agent memory，复用 `data/processed/agent_sessions.sqlite`；接入意图理解与偏好软约束。
2. `cache_service.py`：embedding 查询缓存（LRU）+ 检索结果缓存；相同 query 二次调用不打 embedding API。
3. `observability.py`：结构化日志 / trace / 关键指标；`/health`（或 `/api/meta/system-status`）暴露 rag/faiss/amap/memory/cache 各子系统状态，让"是否真生效"可观测。
4. quality gates：移植门禁脚本，纳入 CI。
- **退出标准**：四个子系统各有读写/命中单测；/health 能显示各子系统状态。

### Phase 5 — 验证（证明"功能不缺失"）

1. 合并两条分支的全部测试到新主干，全绿。
2. `runner.py` **新增 `city="hefei"` 的端到端 case**（现有 8 个 case 全是上海 seed，没覆盖真实 RAG 链路）。
3. 真实链路冒烟：配 embedding/amap key → `rag_build` 构建 FAISS → pool/plan/replan 的 provenance 出现 `semantic_*`、距离来自高德。
4. 逐条勾"功能不缺失检查表"，全部勾完才算重构完成。
- **退出标准**：全测试通过 + 检查表 100% + 真实合肥链路冒烟通过。

---

## 4. 功能不缺失检查表（核心交付，逐条勾）

> 重构"完成"的唯一标准 = 下表全部 ✅，且每条都有对应测试/证据。

- [ ] 真实合肥 DB 可读（文件名无空格），`list_by_city("hefei")` 返回非空
- [ ] 三表结构与类目归一化行为不变（原单测通过）
- [ ] FAISS 索引含 poi_profile + ugc_review 两类文档，数量 > 0
- [ ] sidecar 元数据可按 city / source_type / category 正确过滤
- [ ] 多通道召回 + 证据聚合 + provenance 行为与 real-rag-upgrade 一致
- [ ] feature_bucket 兜底在无 embedding/索引时仍可召回
- [ ] 分层降级：无 key / 索引缺失 / 高德缺失，主链路均不崩
- [ ] 高德路由生效，haversine 作降级；distance_penalty 真正参与评分
- [ ] agent memory 读写正常，会话偏好接入意图/软约束
- [ ] embedding/检索缓存命中（二次查询不打 API）
- [ ] observability：/health 暴露各子系统状态；关键链路有 trace
- [ ] quality gates 纳入 CI 并通过
- [ ] 三风格求解 / 校验 / 修复 / 重规划原行为不变
- [ ] runner.py 新增 hefei e2e case 通过；真实 RAG 链路冒烟通过
- [ ] 文档（current-architecture / README）与新主干一致，城市口径统一

---

## 5. 风险与回滚

- **FAISS 无元数据过滤**：最大技术风险。靠 sidecar + 过采样后过滤解决；过滤后可能凑不够 `top_k` → 自动放大 `top_k * N` 重取。需在 Phase 2 单测覆盖"过滤后补齐"。
- **longcat-api 细节未知**：方案以提交信息推断，Phase 0 盘点不到位会导致迁移遗漏 → 把盘点设为强制门禁，矩阵清零"待盘点"才进 Phase 1。
- **增量回滚**：每 Phase 独立提交、独立可测；旧两分支保留为对照，任一 Phase 失败可回退到上一个稳定提交。
- **真实链路未验证的历史教训**：本次必须以"hefei e2e + provenance 出现 semantic_*"作为硬验收，避免再次"改了但没证明生效"。
- **我无法跑 git 的限制**：Phase 0 的逐文件盘点需你在本机执行，或沙箱恢复后我用 git 补全；在此之前矩阵的"待盘点"行不可省略。

---

## 6. 分支与提交策略

- 新分支：`codex/unified-refactor`，从 `main` 切出。
- 每个 Phase 一组提交，阶段末跑全量测试 + 对应检查表条目。
- 合并回 main 前：检查表 100% + runner（含 hefei case）全绿。
- 旧分支 `codex/longcat-api`、`codex/real-rag-upgrade` 在合并完成前**不删除**，作为能力对照与回滚参照。

---

## 7. 建议落地顺序（投入产出）

1. **Phase 0 盘点**（最高优先，定成败）：没有它，"功能不缺失"无从保证。
2. **Phase 1 + 2**：FAISS 底座 + 检索层，让"检索策略更新"真正以 FAISS 跑起来并被测试覆盖。
3. **Phase 3**：高德 + 距离进评分，补回即时本地场景核心体验。
4. **Phase 4**：记忆/缓存/可观测/质量门，把 longcat-api 的工程能力并回。
5. **Phase 5**：端到端验证 + 检查表清零。

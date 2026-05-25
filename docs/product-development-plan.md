# AIroute 面向成品的开发计划

> 目标：把当前"工程基线健康、P0/P1 已落地"的状态，推进到一个**可端到端演示的真实合肥即时路线成品**。
> 本计划按里程碑组织，每个里程碑标注 **demo 阻断 / 验收标准**，并在最后给出成品验收清单（DoD）。

---

## 0. 当前基线（已验证）

工程质量门已通过：

- 后端 `PYTHONPATH=backend python -m pytest backend/tests -q` → **116 passed, 2 skipped**
- 前端 `npm test -- --run` → **19 passed**
- `npm run build` → 通过
- `git diff --check` → 通过

已完成的能力（在当前 `codex/real-rag-upgrade` 分支）：

- **P0**：DB 文件名规范化、城市错配兜底移除（`data_warning`）、RAG 可观测（`/health`）、距离/就近入评分与召回。
- **P1**：本地语义同义词扩展、类目过滤进 Chroma `where`、embedding 查询缓存。
- **部分 P2/P3**：营业时间缺失改 `warning`、抽出 `category_policy` / `location_context` 消除跨文件重复。

> 待确认：2 个 skipped 测试是哪两个（很可能是"真实 DB smoke"和"需要 key 的 LLM 集成"）。成品阶段**真实 DB smoke 应当真正跑起来**，不能长期 skip。列入 M1。

---

## 1. 成品定义（Definition of Done）

"最终成品"= 一条**端到端、可对外演示**的真实本地即时路线产品，满足：

1. 真实合肥 POI 数据 + **真 RAG 生效**（语义召回带 `provenance` 与真实证据，而非降级关键词）。
2. **就近合理**：基于真实距离/通勤时间排路线，可按出发点变化。
3. **可用移动端 UI**：地图、时间轴、备选替换、对话调整完整，空态/加载体验顺滑。
4. **LLM 智能**：意图解析与解释走真模型，且无 key 时稳定降级。
5. **稳定降级**：任一外部能力（embedding/高德/LLM）不可用仍能完成主链路。
6. **可观测、可部署**：关键链路有日志/指标，CI 绿，容器可起。

---

## 2. 关键决策（建议先拍，影响后续做法）

**是否执行 unified-refactor（切新分支 + 全量改 FAISS + 并回 longcat-api）？**

- 现状：测试已在当前 **Chroma 分支**全绿，P0/P1 完成。
- `codex/longcat-api` 分支已有现成的 **高德路由 / agent memory / observability / cache / quality gates**。

两条路：

| 路线 | 优点 | 代价 | 适用 |
|---|---|---|---|
| **A. 当前 Chroma 分支增量补齐**（推荐用于成品冲刺） | 不动已绿的基线，风险低、交付快 | 保留 Chroma；高德/记忆等需从 longcat-api **cherry-pick** 而非整分支合并 | 时间紧、以演示成品为目标 |
| **B. unified-refactor（FAISS 新分支）** | 引擎统一、并回全部工程能力 | 检索层重写 + 重新验证，工作量与风险最大 | 赛后长期演进、有明确规模/性能诉求 |

**建议**：成品冲刺期走 A，把 longcat-api 的高德/记忆/可观测/缓存按需 cherry-pick 进来；FAISS 全量重写留到赛后。除非你坚持 B，否则下面里程碑按 A 描述（核心里程碑大多与引擎无关，切换成本可控）。

---

## 3. 里程碑

### M1 · 坐实真实链路（demo 阻断，最高优先）

- [ ] 确认 2 个 skipped 测试是什么；让**真实 DB smoke 真正运行**并通过（行数/类目分布/UGC 覆盖达标）。
- [ ] 配 `EMBEDDING_API_KEY` → `python -m app.repositories.rag_index build --city hefei --reset` → `/health` 显示 `collection_count>0`、`embedding_configured=true`。
- [ ] 修 `pool._score_poi` 距离**双算**（`profile_score` 已含 `distance_penalty`，外面又减一次）。
- **验收**：真实合肥跑 pool/plan，候选与路线卡片出现 `semantic_*` provenance + 真实 UGC 证据；`/health` 证明 RAG 非降级。

### M2 · 就近与真实距离（核心体验，demo 阻断）

- [ ] **出发点经纬度打通**：前端定位/地图选点 → `origin_latitude/longitude(/radius)` 传入 pool/plan；profile 的"出发区域"落到坐标。
- [ ] 接**高德**距离/时长（cherry-pick longcat-api 的 `amap_client`），`estimate_transport` 优先高德、haversine 降级；`amap_key` 落地。
- [ ] 在真实链路验证：距离进评分、半径过滤生效。
- **验收**：改变出发点 → 路线顺序与通勤时间随之变化；半径外 POI 不进候选。

### M3 · 路线质量与重规划（成品质感）

- [ ] 求解器从 greedy + 最近邻 → **insertion + 2-opt** 局部搜索，目标含旅行时间/步行/排队/节奏。
- [ ] partial replan 引入**"已完成站点/当前位置"**，雨天/延误只重排剩余站点。
- [ ] 补齐 replan 控件：亲子友好、老人友好、少走路、雨天室内、压缩到 N 小时、加咖啡。
- **验收**：同候选集下总步行/时长不劣于旧版；雨天/延误保留已完成站点；各控件可用且重校验通过。

### M4 · LLM 与解释（智能感）

- [ ] 配 LLM key，验证意图解析与解释生成走**真模型**；无 key 稳定降级到规则。
- [ ] 解释可追溯到评分项 / UGC / `provenance`，无未支撑的虚构信息。
- **验收**：有 key 时意图/解释走真 LLM；断网/无 key 时主链路不崩。

### M5 · 前端成品化（门面，demo 阻断）

- [ ] 接入后端已产出的新字段：`distance_meters`、`data_warning`、`retrieval_provenance`、`evidence_snippets`、`/health` 状态。
- [ ] 地图 / 时间轴 / 备选一键替换 / 对话调整 UI 完整，**移动端适配**。
- [ ] 空态（`city_data_unavailable` 友好提示）与加载（**主路线先渲染、AI 解释异步**）。
- **验收**：移动端完整跑通"生成路线 → 替换备选 → 对话调整"；空态/加载体验顺滑。

### M6 · 数据与内容质量

- [ ] 补全营业时间数据（让 `poi_closed` 校验真正生效，而非只有 `opening_hours_unknown` warning）。
- [ ] POI 字段完整度：封面图、价格、UGC 证据数量/质量。
- [ ] 合肥各区/各类目覆盖度抽样核查。
- **验收**：抽样 POI 字段完整；营业时间校验对闭店时段能拦截。

### M7 · 上线工程化

- [ ] 文档同步：`current-architecture.md`（删已不存在文件引用）、README 城市口径统一。
- [ ] `runner.py` 新增 `city="hefei"` 端到端 case（目前 8 个全是上海 seed）。
- [ ] 可观测补全：结构化日志 / trace / 关键指标（不止 `/health`）。
- [ ] `.env` 规范（embedding/amap/llm key）、`Dockerfile` 起容器验证、CI 跑测试 + quality gates。
- [ ] （若决定并回 longcat-api）移植 memory / cache / quality gates。
- **验收**：CI 绿；容器可起；hefei e2e 通过。

---

## 4. 推荐冲刺顺序（时间紧时的最短成品路径）

```text
M1 (坐实真RAG+真实DB)  →  M2 (出发点+高德)  →  M5 (前端接入新字段)
        └── 以上打通"真实合肥 + 真RAG + 就近 + 可用UI"一条完整可演示链路
然后 M3/M4 提质（路线质量、LLM 解释）  →  M6/M7 收尾（数据、文档、部署、CI）
```

把 M1+M2+M5 作为"能开演示"的最小集，其余为加分项。

---

## 5. 风险与依赖

- **外部 key 依赖**：embedding / 高德 / LLM key 未就绪会卡 M1/M2/M4，需尽早申请配置。
- **真实数据规模未知**：M1 的 smoke 阈值是否达标待验证；数据不足会导致路线空或全兜底。
- **分支决策未定**：第 2 节不拍板会让 M2（高德）、M7（记忆/可观测）反复返工。
- **环境**：本地能跑通测试即可；CI 与容器需单独验证。

---

## 6. 成品验收清单（DoD，逐条勾）

- [ ] 后端 + 前端测试全绿，真实 DB smoke **运行而非 skip**
- [ ] 真实合肥数据达标，`/health` 证明 RAG 生效（非降级）
- [ ] 出发点可传入，路线就近合理，距离来自高德
- [ ] 求解器为约束化优化；partial replan 保留已完成站点；replan 控件齐全
- [ ] LLM 意图/解释走真模型且可降级；解释可追溯
- [ ] 移动端 UI 完整（地图/时间轴/备选/对话），空态与加载体验顺滑
- [ ] 营业时间等数据完整，校验真正生效
- [ ] 文档同步、CI 绿、容器可起、hefei e2e 通过
- [ ] 全链路在断网/无 key 时仍可降级完成 demo

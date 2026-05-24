# RAG 改进方案与修改说明

> 适用范围：`backend/app` 下的检索链路（`repositories/rag_index.py`、`llm/embedding.py`、`services/retrieval_service.py`、`services/ugc_service.py`、`services/pool_service.py`）。
> 本文只覆盖**开发改动本身**：每条改动给出「为什么改 / 现状定位 / 具体改法 / 影响与风险 / 验证方式」。

---

## 0. 现状一句话定位

当前 RAG 是一个 **"POI 画像级语义召回"** 系统：每个 POI 被压成一段画像文本 → 远程 embedding API → 存入 Chroma 集合 `poi_profiles` → query 时按城市做向量召回，结果既作为候选池来源、又作为打分里的 `semantic` 维度（权重 0.24）。

它能跑通"语义召回 POI"，但有四个工程缺口需要修复：距离度量可能算错、UGC 没有作为独立检索单元（与赛题"根据 UGC 串联"不完全契合）、展示证据与用户需求解耦、缺乏可观测与查询缓存。

---

## 1. 改动总览

| 优先级 | 改动 | 类型 | 主要文件 | 预计工作量 |
|---|---|---|---|---|
| **P0** | Chroma 距离度量改为 cosine | 正确性 Bug | `rag_index.py` | 0.5h（含重建索引） |
| **P1** | UGC 评论升级为独立检索单元 | 贴赛题/能力 | `rag_index.py`、`retrieval_service.py`、`schemas/rag.py` | 0.5–1d |
| **P2** | `get_highlight_quotes` 按需求相关性挑选 | 质量 | `ugc_service.py` | 1h |
| **P3** | 查询 embedding 增加缓存 | 性能 | `embedding.py` | 1h |
| **P4** | 检索失败可观测（日志/计数） | 可观测性 | `retrieval_service.py` | 0.5h |
| **P5** | 候选轻量重排（可选） | 精度 | `pool_service.py` / 新增 reranker | 0.5d |

建议落地顺序：**P0 → P4 → P2 → P3 → P1 → P5**。P0/P4/P2/P3 都是低风险局部改动，可先合入；P1 是能力升级、改动面最大，单独成一个分支。

---

## 2. P0 — Chroma 距离度量改为 cosine（正确性 Bug）

### 为什么改

`ChromaVectorIndex.query()` 用 `score = max(0.0, 1.0 - distance)` 把距离换算成相似度。这个公式**只在余弦距离下成立**。但创建集合时：

```python
# rag_index.py 现状
self._collection = client.get_or_create_collection(self.collection_name)
```

没有指定 `hnsw:space`，Chroma 默认使用 **L2（欧氏距离平方）**。对近似单位长度的 OpenAI embedding，L2² ≈ 2 − 2·cos，正确换算应是 `cos = 1 − distance/2`，而代码用的是 `1 − distance`。结果是 **semantic 相似度被系统性低估甚至被 `max(0, …)` 截成 0**，直接拉低 `_score_poi` 里权重 0.24 的语义维度，让向量召回的排序优势失效。

### 现状定位

- `backend/app/repositories/rag_index.py` → `_get_collection()` 第 137 行附近
- 同文件 `query()` 第 112 行 `score = max(0.0, 1.0 - float(distance or 0.0))`

### 具体改法

建集合时声明余弦空间，这样既符合 `1 − distance` 的换算，又是文本语义检索的标准选择：

```python
# rag_index.py，_get_collection 内
if self._collection is None:
    self._collection = client.get_or_create_collection(
        self.collection_name,
        metadata={"hnsw:space": "cosine"},
    )
```

`query()` 里的 `score = max(0.0, 1.0 - distance)` 在 cosine 空间下即为 `cosine_similarity`，**无需再改**（Chroma 的 cosine distance = 1 − cos，故 1 − distance = cos）。

> 注意：`hnsw:space` 只在集合**首次创建**时生效。已建好的 `./data/chroma` 必须重建：
> ```bash
> python -m app.repositories.rag_index build --reset
> ```

### 影响与风险

只影响相似度数值与候选排序，不改变接口与数据结构；唯一前置动作是重建向量库。风险极低。

### 验证方式

- 重建后用同一 query 调 `RetrievalService.retrieve`，确认返回的 `score` 落在合理区间（强相关项明显高于弱相关项，不再大面积为 0）。
- 加一个单测：对一个明显相关 query 与一个无关 query，断言相关 query 的 top1 `score` 显著更高。

---

## 3. P1 — UGC 评论升级为独立检索单元（最贴赛题）

### 为什么改

赛题是"**根据 UGC 串联多个 POI**"。当前 `build_poi_document` 只把 **第 0 条** `highlight_quote` 拼进画像（"证据摘要"字段），其余 UGC 评论既没切块、也没单独向量化：

```python
# rag_index.py 现状
evidence = poi.highlight_quotes[0].quote if poi.highlight_quotes else ""
```

也就是说现在是"**用 UGC 加工出的画像**做检索"，而不是"**检索 UGC 本身**再归因到 POI"。这会带来两个问题：评委追问"UGC 到底参与了哪一步检索"时答案偏弱；用户输入的细粒度需求（如"适合带老人""出片"）无法命中具体某条评论。

### 现状定位

- `rag_index.py` → `build_poi_document()`（只用第 0 条 quote）、`upsert_pois()`、`query()`
- `schemas/rag.py` → `EvidenceSnippet.source_type` 已支持多类型，但当前只产 `poi_profile`
- `retrieval_service.py` → `retrieve()` 假设一行就是一个 POI

### 具体改法

思路：在原 `poi_profile` 文档之外，**为每条 UGC 评论各建一个 doc**（`source_type="ugc_review"`），检索时召回评论，再**按 `poi_id` 聚合**回 POI，保留最相关那条评论作为证据。

新增评论文档构建：

```python
# rag_index.py 新增
def build_ugc_documents(poi: PoiDetail) -> list[RagDocument]:
    docs: list[RagDocument] = []
    for i, q in enumerate(poi.highlight_quotes):
        if not q.quote:
            continue
        docs.append(
            RagDocument(
                doc_id=f"ugc_review:{poi.id}:{i}",
                poi_id=poi.id,
                text=q.quote,
                metadata={
                    "poi_id": poi.id,
                    "city": poi.city,
                    "category": poi.category,
                    "source_type": "ugc_review",
                },
            )
        )
    return docs
```

`upsert_pois` 同时灌入画像文档与评论文档（同一集合，用 `source_type` 区分）：

```python
documents = [build_poi_document(poi) for poi in pois]
for poi in pois:
    documents.extend(build_ugc_documents(poi))
```

`query()` 增加 `source_types` 过滤参数，并把 `where` 写成多条件：

```python
def query(self, *, text, city, top_k, category_filters=None, source_types=None):
    ...
    where = {"city": city}
    if source_types:
        where = {"$and": [{"city": city}, {"source_type": {"$in": list(source_types)}}]}
    result = collection.query(query_embeddings=[embedding],
                              n_results=max(top_k * 4, top_k),  # 评论更碎，多召回
                              where=where,
                              include=["documents", "metadatas", "distances"])
```

`RetrievalService.retrieve()` 在拿到行后**按 poi_id 聚合**（取该 POI 命中评论里的最高分作为 POI 分，最相关评论作为 evidence，provenance 记为 `semantic_ugc_review`）：

```python
best: dict[str, dict] = {}
for row in rows:
    pid = str(row.get("poi_id") or "")
    if not pid:
        continue
    if pid not in best or row["score"] > best[pid]["score"]:
        best[pid] = row
# 之后用 best.values() 走原有的城市/预算/排队过滤与封装逻辑
```

### 影响与风险

- 向量库条数从 ~POI 数 增长到 ~POI 数 + 评论数，存储与构建时间上升（仍是小数据量，可控）。
- `retrieve()` 返回结构不变（仍是 `list[RetrievedPoi]`），**下游 `pool_service` 无需改**；只是 evidence 现在来自真实评论、provenance 更准确。
- 风险点在"评论召回后聚合"逻辑，需保证去重与城市过滤仍生效。

### 验证方式

- 重建索引后，对"适合带老人""出片好看"等细粒度 query，确认 evidence 文本是**具体评论原文**而非整段画像。
- 单测：构造两条对立评论的 POI，断言不同 query 命中不同评论。

---

## 4. P2 — `get_highlight_quotes` 按需求相关性挑选

### 为什么改

`UgcService.get_highlight_quotes(poi_id, intent_keywords, max_count)` 签名里有 `intent_keywords`，但实现**完全忽略它**，无脑返回前两条：

```python
# ugc_service.py 现状
quotes = poi.highlight_quotes[:max_count]
```

结果是不管用户要"安静"还是"热闹"，展示的引用都一样，证据与需求解耦。

### 现状定位

`backend/app/services/ugc_service.py` → `get_highlight_quotes()`

### 具体改法

先做一版**零依赖的词面相关性排序**（命中 `intent_keywords` 的评论排前），后续可平滑替换为 P1 的向量召回结果：

```python
def get_highlight_quotes(self, poi_id, intent_keywords, max_count=2):
    poi = self.repo.get(poi_id)
    kws = [k for k in (intent_keywords or []) if k]

    def relevance(q) -> int:
        text = q.quote or ""
        return sum(1 for k in kws if k in text)

    ranked = sorted(poi.highlight_quotes, key=relevance, reverse=True)
    # 全 0 命中时退化为原始顺序，保证不劣于现状
    chosen = ranked[:max_count] if any(relevance(q) for q in ranked) else poi.highlight_quotes[:max_count]
    return [UgcSnippet(quote=q.quote, source=q.source,
                       date=q.review_date.isoformat() if q.review_date else None)
            for q in chosen]
```

### 影响与风险

纯局部改动，无命中时行为与现状一致（不会变差）。风险极低。

### 验证方式

单测：同一 POI 传不同 `intent_keywords`，断言返回的 quote 顺序/内容随关键词变化；传空关键词时与旧行为一致。

---

## 5. P3 — 查询 embedding 增加缓存

### 为什么改

`EmbeddingClient.embed_texts` 每次都发起一次远程 HTTP（`/embeddings`）。在 chat 调整、replan 等场景里，**相同或相近的 query 会被反复 embed**，既增加延迟又增加费用。索引构建是离线批量、不需要缓存，但**在线查询**值得缓存。

### 现状定位

`backend/app/llm/embedding.py` → `EmbeddingClient.embed_texts`

### 具体改法

新增一个带 LRU 的单条查询入口 `embed_query`，键为 `(model, text)`；批量索引仍走原 `embed_texts`，互不影响：

```python
from collections import OrderedDict

class EmbeddingClient:
    _cache: "OrderedDict[tuple[str, str], list[float]]" = OrderedDict()
    _CACHE_MAX = 512

    def embed_query(self, text: str) -> list[float]:
        model = get_settings().embedding_model
        key = (model, text)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        vec = self.embed_texts([text])[0]
        self._cache[key] = vec
        self._cache.move_to_end(key)
        if len(self._cache) > self._CACHE_MAX:
            self._cache.popitem(last=False)
        return vec
```

`ChromaVectorIndex.query` 把单条 query 的 embedding 改为走缓存入口：

```python
# 原：embedding = self.embedding_client.embed_texts([text])[0]
embedding = self.embedding_client.embed_query(text)
```

### 影响与风险

类级缓存在单进程内共享；若未来多 worker 部署，可平滑替换为 Redis 后端（接口不变）。注意缓存键含 `model`，换模型不会取到旧向量。风险低。

### 验证方式

单测：用 mock 的 `embed_texts` 计数，连续两次 `embed_query` 相同文本，断言底层只被真正调用一次。

---

## 6. P4 — 检索失败可观测（日志/计数）

### 为什么改

`RetrievalService.retrieve` 里两处 `except Exception: return []` 会**静默吞掉所有错误**。线上一旦 embedding 服务异常、Chroma 损坏，检索会持续返回空、悄悄退化到关键词兜底，而你**完全无感知**。

### 现状定位

`backend/app/services/retrieval_service.py` → `retrieve()` 第 29–32 行的 `except`

### 具体改法

至少加结构化日志（项目其他模块若已有 logger，复用其约定）：

```python
import logging
logger = logging.getLogger(__name__)

try:
    rows = self.vector_index.query(...)
except EmbeddingUnavailable as exc:
    logger.warning("retrieval embedding unavailable: %s", exc)
    return []
except Exception:
    logger.exception("retrieval failed unexpectedly")
    return []
```

如已接入指标体系，可再加一个 `retrieval_empty_total` / `retrieval_error_total` 计数器，便于报警。

### 影响与风险

仅增加日志，不改变返回行为。风险极低。

### 验证方式

注入一个会抛异常的假 `vector_index`，断言 `retrieve` 仍返回 `[]` 且日志被记录。

---

## 7. P5 — 候选轻量重排（可选）

### 为什么改

`pool_service._retrieve_candidates` 一次召回 `top_k=80`，直接进入加权打分。召回阶段重在"全"，但 top 区精度可再提升。数据量小时收益有限，属于锦上添花。

### 具体改法（建议先用规则版，不引入重模型）

在打分后、截断 `[:24]` 前，对 top-N 候选做一次"检索分 × 画像分"的几何平均重排，弱化单一信号偏置：

```python
def _rerank(self, scored):
    # scored: list[(score, poi)]，已含 retrieval 信号
    return sorted(scored, key=lambda it: it[0], reverse=True)  # 占位：可替换为多信号融合
```

若要上 cross-encoder（`sentence_transformers` 已在依赖中），仅对 top-30 重排以控延迟。**面试加分项，非必需**。

### 验证方式

A/B：固定 query，对比重排前后 top-5 的人工相关性判断。

---

## 8. 落地检查清单

- [ ] P0：集合声明 `hnsw:space=cosine`，并执行 `build --reset` 重建
- [ ] P0：新增"相关 query 分数显著高于无关 query"单测
- [ ] P4：`retrieve` 两处 `except` 加日志
- [ ] P2：`get_highlight_quotes` 接入关键词相关性，补单测
- [ ] P3：`embed_query` LRU 缓存 + 命中单测
- [ ] P1：`build_ugc_documents` + `upsert` 灌评论 + `retrieve` 按 poi_id 聚合，重建索引，补"不同 query 命中不同评论"单测
- [ ] P5（可选）：top 区重排

> 提示：P0 与 P1 都需要 **重建向量库**，建议合并到同一次 `build --reset`，避免重复全量 embedding。

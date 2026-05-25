# Unified Refactor Capability Checklist

This document records the Phase 0 file-level inventory for the unified refactor branch.

## Source Branch Inventory

### `codex/longcat-api` / `origin/main`

| Capability | Files |
|---|---|
| Agent runtime and tool orchestration | `backend/app/agent/*`, `backend/app/api/routes_agent.py` |
| Agent memory and user facts | `backend/app/agent/store.py`, `backend/app/agent/user_memory.py`, `backend/app/repositories/session_vector_repo.py`, `backend/app/schemas/user_memory.py` |
| UGC FAISS recall | `backend/app/repositories/ugc_vector_repo.py`, `backend/repositories/embedding_cache.py`, `scripts/build_retrieval_index.py` |
| Cache | `backend/app/cache_backend.py`, `backend/app/llm/cache.py`, `backend/app/repositories/embedding_cache.py`, `backend/app/services/amap/cache.py` |
| Observability | `backend/app/observability/logging.py`, `backend/app/observability/metrics.py`, `backend/app/observability/tracing.py` |
| Amap routing | `backend/app/services/amap/*`, `backend/app/api/routes_route.py`, `frontend/src/pages/AmapRoutePage.tsx` |
| Quality gates and prompt regression | `backend/tests/test_agent_quality.py`, `backend/tests/test_quality_engineering.py`, `backend/tests/test_prompt_regression.py` |

### `codex/real-rag-upgrade`

| Capability | Files |
|---|---|
| RAG contract | `backend/app/schemas/rag.py` |
| Dual-source POI/UGC documents | `backend/app/repositories/rag_index.py` |
| Retrieval orchestration and provenance | `backend/app/services/retrieval_service.py` |
| Three-table SQLite loader | `backend/app/repositories/sqlite_poi_repo.py` |
| Category policy and radius helpers | `backend/app/services/category_policy.py`, `backend/app/services/location_context.py` |
| Pool/plan evidence fields | `backend/app/schemas/pool.py`, `backend/app/schemas/plan.py`, `frontend/src/types/pool.ts`, `frontend/src/types/plan.ts` |
| Regression tests | `backend/tests/test_real_rag_upgrade.py`, `backend/tests/test_multitype_rag_recall.py`, `backend/tests/test_db_retrieval_followup.py` |

## Unified Branch Decisions

| Capability | Unified implementation |
|---|---|
| Vector engine | `backend/app/repositories/faiss_index.py` with JSONL sidecar metadata in `backend/app/repositories/faiss_meta.py` |
| Document build | `backend/app/repositories/rag_build.py` builds `poi_profile` + `ugc_review` documents |
| Retrieval contract | `backend/app/schemas/rag.py`, `backend/app/services/retrieval_service.py` |
| Existing SQLite FTS/bucket recall | Preserved in `backend/app/services/poi_retrieval_service.py` |
| Pool fusion | `backend/app/services/pool_service.py` merges semantic FAISS results with SQLite FTS/bucket results |
| Fallback when DB/index missing | Hefei seed fallback in `backend/app/repositories/seed_data.py`; FAISS/embedding errors return empty semantic results |
| Memory/cache/observability/Amap | Existing modules are preserved from `origin/main`; deeper unified integration is tracked as remaining work below |

## Functional Checklist

- [x] Hefei POI fallback exists without local SQLite.
- [x] Three-table SQLite loader maps `poi_feature_index.derived_category`.
- [x] UGC evidence rows become `PoiDetail.highlight_quotes`.
- [x] FAISS index stores `poi_profile` and `ugc_review` rows.
- [x] Sidecar metadata filters by `city`, `category`, and `source_type`.
- [x] Retrieval aggregates evidence and preserves `semantic_*` provenance.
- [x] Pool candidates expose retrieval provenance and evidence snippets.
- [x] Existing SQLite FTS/bucket recall tests still pass.
- [x] Agent memory, cache, observability, Amap modules remain present from `origin/main`.
- [x] Full backend suite passes after final integration.
- [x] Frontend tests/build pass after final integration.
- [ ] Real local FAISS smoke test is run when embedding model/data files are available.

## Known Remaining Work

These items are not complete in this branch and should not be treated as delivered by the unified refactor PR:

- [ ] Amap routing is not used by the solver or candidate scoring path; `solver/distance.py` still uses haversine fallback for route ordering and metrics.
- [ ] The solver remains greedy; P2-1 optimization work is still pending.
- [ ] Partial replan has no locked "completed stops" concept yet; P2-3 is still pending.
- [ ] Agent memory is preserved from `origin/main`, but it has not been newly unified with the FAISS retrieval contract in this branch.
- [ ] Observability modules and `/health` status exist, but full tracing/metrics coverage for the unified retrieval flow is not complete.
- [ ] Embedding cache exists; retrieval-result cache for repeated semantic queries is not implemented.
- [ ] Quality gates and prompt regression tests exist in the tree, but no new CI gate wiring was added here.

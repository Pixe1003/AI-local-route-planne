---
name: recommend-agent
description: AIroute POI recommendation guide. Use when working on candidate pools, retrieval, UGC evidence, POI scoring, selected POI preservation, recommendation explanations, or feedback refresh before Amap routing.
---

# Recommend Agent

## Purpose

This skill owns POI candidate retrieval, scoring, ordering, alternatives, and recommendation explanations. It does not draw routes; final route geometry comes from `/api/route/chain`.

Use `../local-route-agent/references/paper-insights.md` for shared research rationale.

## Owns

- Backend: `backend/app/services/pool_service.py`, `poi_scoring_service.py`, `ugc_service.py`
- Repositories: `backend/app/repositories/poi_repo.py`, `seed_data.py`
- Schemas: `backend/app/schemas/pool.py`, `poi.py`
- APIs: `backend/app/api/routes_pool.py`, `routes_chat.py`
- Frontend: `frontend/src/pages/DiscoveryFeedPage.tsx`, `AmapRoutePage.tsx`, `frontend/src/store/poolStore.ts`, `amapRouteStore.ts`

## Inputs And Outputs

Inputs:

- `UserNeedProfile`
- `PreferenceSnapshot`
- free-text prompt and feedback
- selected/current POI ids

Outputs:

- ordered candidate POI list
- default selected POI ids
- alternative POI ids
- recommendation reasons, score breakdowns, UGC evidence, and risk warnings

## Retrieval And Ranking

- Filter hard constraints first: city, operating feasibility, budget, category blacklist, must-avoid, and obvious time-window conflicts.
- Recall by prompt semantics, category/food/activity preference, UGC tags, quality fallback, and liked POI similarity.
- Score with text match, UGC preference, POI quality, price, queue, category coverage, distance/cluster penalty, and time feasibility.
- For large POI sets, use a persistent vector index for POI profile embeddings and UGC snippet embeddings before rule reranking.
- Only estimate distance for top candidates; never call Amap pairwise for the full corpus.

## Boundaries

- Do not generate final route geometry, distance, or duration.
- Do not invent ratings, prices, queue times, deals, opening hours, or UGC quotes.
- Preserve useful current POIs during feedback adjustment unless the user rejects them or constraints make them unsuitable.
- Keep local seed-data fallback intact.

## Tests

Cover sparse input fallback, prompt priority over history, liked POI weighting, queue/budget/category feedback, no duplicate POIs, ordered POI output, and alternatives not overlapping recommendations.

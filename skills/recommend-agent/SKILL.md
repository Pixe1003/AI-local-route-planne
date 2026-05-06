---
name: recommend-agent
description: AIroute Recommend Agent 的开发、修改、评审和测试指南。Use when working on POI candidate pools, retrieval, candidate provenance, UGC evidence, POI scoring inputs, pool chat refresh, selected POI preservation, or recommendation explanations before route planning.
---

# Recommend Agent

## Purpose

Use this skill to build and review AIroute's candidate POI pool. This Agent finds plausible POIs, attaches evidence and risks, supports user selection, and hands route planning a traceable candidate set.

Use `../local-route-agent/references/paper-insights.md` for the shared research rationale. Keep this skill focused on candidate discovery and evidence.

## Owns

- Backend: `backend/app/services/pool_service.py`, `poi_scoring_service.py`, `ugc_service.py`
- Repositories: `backend/app/repositories/poi_repo.py`, `seed_data.py`, `vector_repo.py`
- Schemas: `backend/app/schemas/pool.py`, `poi.py`
- APIs: `backend/app/api/routes_pool.py`
- Frontend: `frontend/src/pages/RecommendPoolPage.tsx`, `PoolPage.tsx`, `frontend/src/components/PoolGrid.tsx`, `PoiCard.tsx`, `UgcEvidence.tsx`, `frontend/src/store/poolStore.ts`

## Inputs And Outputs

Inputs:

- `UserNeedProfile`
- planning context
- free-text refinements from the recommendation pool chat
- selected/locked POIs

Outputs:

- candidate POI list
- default selected POIs
- recommendation reasons
- UGC snippets/tags
- risk warnings
- provenance for why each POI entered the pool

## Retrieval Strategy

Use multiple retrieval paths before ranking:

- explicit selected POIs
- category and food/activity preference match
- semantic/free-text match
- geographic fit and nearby clusters
- popularity/quality fallback
- UGC tags and route-pattern hints
- cold-start supplements when the user gives sparse input

Merge candidates by POI id, keep provenance, then score.

## UGC Evidence Rules

- Use UGC as evidence and risk detection, not as the only decision source.
- Extract positive tags, negative tags, scene tags, time/weather tags, risk tags, and concise snippets.
- Recommendation reasons should combine user preference, POI attribute, and evidence when available.
- Risk warnings must be concrete: queue, crowding, price, weather exposure, walking burden, or mismatch with party type.

## Boundaries

- Do not generate the final itinerary here.
- Do not drop user-selected POIs unless they are unavailable or violate hard constraints, and record the reason.
- Do not invent ratings, prices, queue times, deals, opening hours, or UGC quotes.
- Keep external API failure fallback intact; the demo must work from local seed data.

## Tests

Cover:

- Sparse input still returns reasonable cold-start candidates.
- Selected POIs are preserved and marked.
- Candidate provenance is available.
- UGC evidence and risk tags appear where data exists.
- Pool refresh respects new user constraints such as "少排队", "更小众", "亲子", or "雨天".
- No duplicate POIs after merging retrieval paths.

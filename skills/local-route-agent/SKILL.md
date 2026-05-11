---
name: local-route-agent
description: AIroute local route recommendation agent guide. Use when working on UGC preference capture, POI recommendation, scoring, route ordering, Amap route rendering, feedback adjustment, or tests for these flows.
---

# Local Route Agent

## Purpose

AIroute is now a POI recommendation and Amap route rendering system. LLMs may parse intent, update constraints, and explain recommendations, but they must not invent final POIs or draw routes. Final POIs come from repository data or connected data sources, and real distance/duration/polyline data comes from Amap.

Use `references/paper-insights.md` for research context when changing recommendation, scoring, validation, or product experience.

## Current Pipeline

`UGC Feed -> PreferenceSnapshot -> POI recommendation pool -> ordered POI ids -> /api/route/chain -> Amap map page -> /api/chat/adjust feedback`

## Specialist Skills

- `../need-profile-agent/SKILL.md`: user need parsing and profile quality.
- `../recommend-agent/SKILL.md`: POI retrieval, candidate pools, UGC evidence, scoring, and feedback refresh.
- `../route-planning-agent/SKILL.md`: backend ordering/feasibility for POI sequences. It does not own map rendering.
- `../replan-agent/SKILL.md`: legacy plan adjustment and current POI recommendation feedback behavior.
- `../trip-manager-agent/SKILL.md`: legacy backend trip compatibility only.

## First Read

- Backend services: `pool_service.py`, `poi_scoring_service.py`, `chat_service.py`, `services/amap/*`, `state.py`.
- Backend APIs: `routes_ugc.py`, `routes_preferences.py`, `routes_pool.py`, `routes_route.py`, `routes_chat.py`.
- Frontend flow: `DiscoveryFeedPage.tsx`, `AmapRoutePage.tsx`, `AmapRouteMap.tsx`, `preferenceStore.ts`, `poolStore.ts`, `amapRouteStore.ts`.
- Route contracts: `backend/app/schemas/route.py`, `frontend/src/types/route.ts`.

## Core Rules

- Do not route the primary frontend flow through `/api/plan/generate`.
- Do not make the LLM generate route geometry, distance, or duration.
- Filter hard constraints before ranking soft preferences.
- Score POIs with explainable factors: semantic match, UGC preference, POI quality, price, queue, category coverage, distance penalty, and time-window feasibility.
- Only call Amap for top candidates or final ordered POIs; never call Amap pairwise for the full POI corpus.
- Feedback such as "less queue", "cheaper", "no malls", or "more local food" should update recommendation constraints/weights, then recompute the Amap route.

## Tests

Cover:

- Preference snapshot and UGC like behavior.
- Prompt priority over historical likes.
- Budget, queue, category, and blacklist filtering or downranking.
- `/api/route/chain` config errors, upstream errors, unknown POIs, segments, totals, and GeoJSON.
- Frontend UGC page, Amap route page, feedback adjustment, and retired route redirects.

## Anti-Patterns

- Treating recommended POIs as an already valid route.
- Letting old trip/plan frontend pages become a second product flow.
- Hiding Amap configuration or upstream failures behind a generic 500.
- Using UGC popularity alone as personalization.
- Making the map wait for long AI explanations before showing route results.

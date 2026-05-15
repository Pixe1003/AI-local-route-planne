---
name: replan-agent
description: AIroute feedback adjustment guide. Use when working on chat-based POI recommendation updates, event classification, legacy plan adjustment, weather/queue/budget/time changes, or tests for these flows.
---

# Replan Agent

## Purpose

Current frontend feedback updates recommended POIs, then reruns `/api/route/chain`. Legacy `RouteReplanner` still exists for backend compatibility tests, but it is not the primary frontend flow.

Use `../local-route-agent/references/paper-insights.md` for shared research rationale.

## Owns

- Current backend: `backend/app/services/chat_service.py`, `pool_service.py`, `state.py`
- Current API: `backend/app/api/routes_chat.py`
- Current frontend: `frontend/src/pages/AmapRoutePage.tsx`
- Legacy backend compatibility: `route_replanner.py`, `route_validator.py`, `route_repairer.py`, `schemas/plan.py`

## Current Feedback Rules

- Without `plan_id`, `POST /api/chat/adjust` updates recommendation constraints and returns `recommended_poi_ids` plus `alternative_poi_ids`.
- Feedback should preserve reasonable current POIs, remove or downrank rejected categories, and favor lower queue/cost/distance when requested.
- The frontend must recompute the Amap route after recommendation changes.
- Do not generate route geometry or distance in chat responses.

## Tests

Cover:

- "less queue" lowers max queue or explains constraint conflict.
- "cheaper" lowers cost or downranks expensive POIs.
- "rain" reduces outdoor-heavy recommendations.
- Category rejection removes matching POIs when alternatives exist.
- Returned recommended and alternative POI ids do not overlap.

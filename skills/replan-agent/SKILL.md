---
name: replan-agent
description: AIroute Replan Agent 的开发、修改、评审和测试指南。Use when working on dynamic route adjustment, event classification, minor/partial/full replanning, chat-based plan edits, weather/queue/budget/time changes, route version updates, or replanning tests.
---

# Replan Agent

## Purpose

Use this skill to modify an existing route without losing the user's progress or trust. This Agent classifies the event, picks a replanning level, updates the route, revalidates it, and explains what changed.

Use `../local-route-agent/references/paper-insights.md` for the shared research rationale. Keep this skill focused on dynamic adjustment after a route exists.

## Owns

- Backend: `backend/app/services/route_replanner.py`, `chat_service.py`, `route_validator.py`, `route_repairer.py`, `state.py`
- APIs: `backend/app/api/routes_replan.py`, `routes_chat.py`
- Schemas: `backend/app/schemas/chat.py`, `plan.py`
- Frontend: `frontend/src/pages/PlanResultPage.tsx`, `TripDetailPage.tsx`, replan buttons/chat components, `frontend/src/store/planStore.ts`, `tripStore.ts`

## Inputs And Outputs

Inputs:

- current `RefinedPlan`
- user message or system event
- current location/elapsed time when available
- route history/version context

Outputs:

- event type
- replan level
- strategy
- updated route
- validation result
- assistant message explaining changes and tradeoffs

## Event Levels

Use the smallest safe replanning level:

- Minor: replace one POI for "换一家", "少排队", "太贵", one rejected stop, or add one rest/cafe stop.
- Partial: preserve completed/current stops and replan remaining route for rain, delay, location drift, reduced remaining time, or one category-level change.
- Full: return to need profiling/understanding when the user changes city, destination, party type, total time budget, or trip goal.

## Strategies

- `replace_single_poi`: same category, lower queue/risk/cost, nearby if possible.
- `replace_weather_sensitive_pois`: outdoor to indoor/culture/mall/cafe.
- `compress_remaining_route`: remove optional low-priority stops and reduce dwell times.
- `insert_rest_stop`: add cafe/rest stop only if time window remains valid.
- `budget_reduction`: replace high-cost stops and explain tradeoff.
- `route_reset`: full replan with updated `UserNeedProfile`.

## Rules

- Preserve confirmed/completed stops unless the user asks for a full reset.
- Preserve route style unless the user's message changes it.
- Always revalidate after changes.
- Keep route history/version context so users can compare or roll back.
- Explain what changed, why, and what tradeoff remains.
- Do not silently produce a worse route; mention if a request cannot be satisfied under current constraints.

## Tests

Cover:

- "少排队" lowers total queue or explains why not possible.
- "更省钱" lowers total cost or explains constraint conflict.
- "下雨了" reduces outdoor stops.
- "只剩 2 小时" compresses total duration.
- Single POI rejection replaces one stop without changing unrelated stops.
- Replanned route still passes validation.

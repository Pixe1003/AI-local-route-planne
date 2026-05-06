---
name: trip-manager-agent
description: AIroute Trip Manager Agent 的开发、修改、评审和测试指南。Use when working on trip persistence, route versions, trip summaries, trip detail pages, plan history, saving generated or replanned routes, restoring context, or replacing in-memory registries.
---

# Trip Manager Agent

## Purpose

Use this skill to make route planning feel like a durable trip product instead of a one-off response. This Agent owns trip records, route versions, summaries, history, restoration, and save/share handoff.

Use `../local-route-agent/references/paper-insights.md` for the shared research rationale. Keep this skill focused on state and lifecycle.

## Owns

- Backend: `backend/app/services/trip_service.py`, `orchestrator.py`, `state.py`
- APIs: `backend/app/api/routes_trips.py`
- Schemas: `backend/app/schemas/trip.py`, route-version fields in `plan.py`
- Frontend: `frontend/src/pages/TripHomePage.tsx`, `TripDetailPage.tsx`, `TripCreatePage.tsx`, `frontend/src/api/trips.ts`, `frontend/src/types/trip.ts`, `frontend/src/store/tripStore.ts`

## Inputs And Outputs

Inputs:

- user id
- `UserNeedProfile`
- candidate pool id or selected POIs
- generated/replanned `RefinedPlan`
- chat/replan history

Outputs:

- `TripSummary`
- `TripRecord`
- `RouteVersion`
- active route version
- restored planning context

## Lifecycle

1. Create or update trip after need profile and/or first plan generation.
2. Save each generated route or replan as a version.
3. Preserve the profile, context, selected POIs, route, validation, warnings, and user-facing explanation.
4. Let the UI show trip summaries and restore detail pages.
5. Support comparison or rollback when multiple versions exist.

## Rules

- Do not store only final text. Store structured route data and enough context to replan.
- Route versions should be immutable records; new replans create new versions or explicit revisions.
- Preserve validation results and warnings with each route version.
- Keep in-memory registries as demo fallback, but design new code so persistent storage can replace them cleanly.
- Avoid coupling trip persistence to one UI page. APIs should support home, detail, result, and replan flows.
- Do not lose selected POIs or user profile when saving a route.

## Tests

Cover:

- Listing trip summaries.
- Saving a first route version.
- Saving a replanned route as a new version.
- Restoring trip detail with profile, route, validation, and history.
- Active version selection.
- Fallback behavior when persistence is local/in-memory.

---
name: route-planning-agent
description: AIroute route ordering and feasibility guide. Use when working on POI ordering, solver heuristics, dwell time, route scoring, validation, repair, dropped POI reasons, or backend compatibility plans.
---

# Route Planning Agent

## Purpose

This skill owns backend POI sequence feasibility. It can order candidate POIs and estimate timing, but the current frontend route rendering must go through `/api/route/chain` and Amap.

Use `../local-route-agent/references/paper-insights.md` for shared research rationale.

## Owns

- Backend: `backend/app/services/plan_service.py`, `solver_service.py`, `route_validator.py`, `route_repairer.py`, `poi_scoring_service.py`
- Solver utilities: `backend/app/solver/distance.py`, `styles.py`
- Schemas: `backend/app/schemas/plan.py`
- Compatibility API: `backend/app/api/routes_plan.py`

There is no current frontend owner for legacy `RefinedPlan` rendering. New user-facing route rendering belongs to `AmapRoutePage.tsx` and `/api/route/chain`.

## Rules

- Validate before presenting any backend-generated plan.
- Model POI ordering as a constrained itinerary problem, not plain text generation.
- Respect start/end, time window, strict budget, required categories, must-visit POIs, and party constraints.
- Use greedy insertion, beam search, local swap, or bounded repair for MVP candidate sizes.
- Produce dropped reasons for selected POIs that cannot fit.
- Never return Amap geometry from this service; true routes are produced by `routes_route.py`.

## Tests

Cover time window, budget, queue, walking, category validation, dropped reasons, dwell time personalization, repair, and unsupported-claim prevention.

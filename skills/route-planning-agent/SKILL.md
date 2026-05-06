---
name: route-planning-agent
description: AIroute Route Planning Agent 的开发、修改、评审和测试指南。Use when working on itinerary generation, route ordering, solver heuristics, dwell time, route scoring, validation, repair, dropped POI reasons, RefinedPlan output, or PlanResult route display.
---

# Route Planning Agent

## Purpose

Use this skill to turn a candidate POI set into executable route plans. This Agent owns ordering, timing, route scoring, validation, repair, dropped reasons, and final plan structure.

Use `../local-route-agent/references/paper-insights.md` for the shared research rationale. Keep this skill focused on itinerary construction and feasibility.

## Owns

- Backend: `backend/app/services/plan_service.py`, `solver_service.py`, `route_validator.py`, `route_repairer.py`, `poi_scoring_service.py`
- Solver utilities: `backend/app/solver/distance.py`, `styles.py`
- Schemas: `backend/app/schemas/plan.py`
- APIs: `backend/app/api/routes_plan.py`
- Frontend: `frontend/src/pages/PlanResultPage.tsx`, `PlanPage.tsx`, `frontend/src/components/PlanTimeline.tsx`, `PlanCompare.tsx`, `PlanMap.tsx`, `frontend/src/store/planStore.ts`

## Inputs And Outputs

Inputs:

- `UserNeedProfile`
- `PlanContext`
- candidate or selected POI ids
- structured intent
- UGC/scoring evidence

Outputs:

- one or more `RefinedPlan` variants
- ordered stops with arrival/departure times
- total time, cost, queue, walking distance, POI count
- validation result
- dropped POI reasons
- route-level tradeoffs and style highlights

## Planning Rules

- Model route planning as constrained itinerary search, not list sorting.
- Respect start/end, time window, strict budget, required categories, must-visit POIs, and party constraints.
- Choose an MVP algorithm that fits the candidate size: greedy insertion, beam search, local swap, or bounded repair. Consider GA/iterated local search only when the candidate set is large enough to justify it.
- Personalize dwell time by category, user interest, party type, time of day, and route style.
- Build distinct route styles only when the tradeoff is real, such as efficient, relaxed, and foodie-first.
- Produce dropped reasons for every user-selected POI that cannot fit.

## Validation Rules

Validate before presenting:

- POI exists in data source.
- Arrival fits opening status when data exists.
- Total time fits the time window.
- Strict budget is not exceeded.
- Required categories and must-visit points are covered.
- Queue, walking, and travel distances do not exceed hard limits.
- Explanation facts match POI attributes, UGC, scores, or validation.

## Repair Rules

Repair with bounded attempts:

- replace closed POI
- replace high-queue POI
- replace over-budget POI
- remove low-priority optional stop
- reorder stops
- insert missing required category
- compress dwell time
- switch outdoor stops to indoor when weather requires it

If no valid route exists, return a clear failure with the tight constraint and suggested relaxation.

## Tests

Cover:

- Time window, budget, queue, walking, and category validation.
- Must-visit preservation or explicit dropped reason.
- Dwell time personalization.
- Route style differences.
- Repair after validation failure.
- No nonexistent POIs or unsupported claims in final plans.

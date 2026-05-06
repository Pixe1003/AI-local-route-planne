---
name: local-route-agent
description: AIroute 本地路线智能规划 Agent 的开发、修改、评审和测试指南。Use when working on the AIroute project route-planning agent, including need profiling/onboarding, POI candidate pools, UGC evidence, POI scoring, itinerary optimization, route validation and repair, explanation generation, dynamic replanning, trip state, mobile route UI, or tests for these flows.
---

# Local Route Agent

## Purpose

Use this skill to change or review AIroute as a controllable local route-planning Agent. Treat the system as a Harness Agent: LLMs may parse intent, coordinate tools, and explain results, but deterministic services must retrieve POIs, score candidates, optimize routes, validate constraints, repair failures, and replan.

For the research basis behind these rules, read `references/paper-insights.md` when making architecture, scoring, validation, replanning, or product-experience decisions.

## Specialist Skills

Use this skill as the umbrella. For focused implementation, use the relevant specialist skill:

- `../need-profile-agent/SKILL.md`: onboarding, slot filling, completeness, `UserNeedProfile`, trip creation inputs.
- `../recommend-agent/SKILL.md`: POI retrieval, candidate pool, UGC evidence, pool chat, selected POIs.
- `../route-planning-agent/SKILL.md`: solver, itinerary ordering, dwell time, validation, repair, dropped reasons.
- `../replan-agent/SKILL.md`: event classification, minor/partial/full replan, route adjustment chat.
- `../trip-manager-agent/SKILL.md`: trip records, route versions, history, persistence, restoration.

## First Read

Before editing behavior, inspect the current implementation and keep changes aligned with it:

- Backend services: `backend/app/services/onboarding_service.py`, `pool_service.py`, `poi_scoring_service.py`, `plan_service.py`, `solver_service.py`, `route_validator.py`, `route_repairer.py`, `route_replanner.py`, `ugc_service.py`, `state.py`.
- Schemas: `backend/app/schemas/onboarding.py`, `plan.py`, `poi.py`, `pool.py`, `trip.py`.
- APIs: `backend/app/api/routes_onboarding.py`, `routes_pool.py`, `routes_plan.py`, `routes_chat.py`, `routes_replan.py`, `routes_trips.py`.
- Frontend flow: `frontend/src/pages/TripCreatePage.tsx`, `RecommendPoolPage.tsx`, `PlanResultPage.tsx`, `TripDetailPage.tsx`, related stores and components.

## Core Principles

- Preserve the pipeline: Need Profile -> Candidate Pool -> UGC Evidence -> Scoring -> Route Optimizer -> Validator/Repairer -> Explanation -> Replanner.
- Do not let the LLM directly invent final routes. Every final POI must come from repository data or an explicitly connected data source.
- Separate POI quality from route quality. A good POI can still be a bad route stop if it breaks time, budget, walking, queue, opening-hours, or sequence constraints.
- Filter hard constraints before ranking soft preferences. Hard constraints include POI existence, operating status, time budget, strict budget, must-visit coverage, category coverage, and infeasible travel.
- Make every reason traceable. Explanations must cite POI attributes, UGC snippets/tags, score breakdowns, user profile fields, or validation results.
- Support dynamic replanning as a first-class flow. Prefer minor replacement when possible, partial replanning for changed context, and full replanning only when the user changes the goal.
- Keep mobile performance in mind. Route explanations and AI-generated text can be asynchronous or cached; the main route should render quickly.

## Workflow

1. Classify the requested change by Agent stage: onboarding, pool/recommendation, scoring, optimization, validation/repair, explanation, replanning, trip persistence, or UI.
2. Identify the owning service and schema before editing. Avoid adding a parallel implementation if an existing service can be extended.
3. Update data contracts first when behavior needs new fields. Keep Pydantic and frontend TypeScript types in sync.
4. Add or adjust deterministic logic in services. Use LLM output only as structured input or natural-language explanation.
5. Update tests for the affected stage and at least one full-flow test when behavior changes across stages.
6. Run targeted tests before claiming completion.

## Module Guidance

### Need Profile / Onboarding

- Extract city, start/end location, time window, budget, party type, activity preferences, food preferences, route style, avoid items, must-visit, and must-avoid.
- Compute completeness and ask follow-up questions when key slots are missing. Do not guess high-risk slots such as exact start location, strict budget, or time window.
- Map party type to route weights: family/senior should increase rest, low walking, safety, and indoor/low-crowd preferences; couple/friends can increase atmosphere, photos, and food/entertainment.

### Candidate Pool / UGC

- Use multi-route retrieval: semantic preference, geography, category, popularity, UGC tags, cold-start fallback, and selected POIs from the user.
- Use UGC as evidence and risk detection, not as the only decision source.
- Extract positive tags, negative tags, scene tags, time/weather tags, risk tags, and concise evidence snippets.
- Keep candidate provenance so explanations can say why a POI entered the pool.

### Scoring

Score POIs with a transparent breakdown:

```text
poi_score =
  user_interest
+ poi_quality
+ context_fit
+ ugc_match
+ service_closure
- queue_penalty
- price_penalty
- distance_penalty
- risk_penalty
```

Route score must also consider sequence coherence, travel time, walking distance, total queue time, budget, time rhythm, category coverage, and fatigue.

### Route Optimization

- Model planning as a constrained itinerary problem, not a plain sorted list.
- MVP algorithms may use greedy, beam search, insertion heuristics, and local search. Consider GA or iterated local search only when candidate count makes exhaustive search unrealistic.
- Respect user-specified start/end locations, time windows, selected POIs, must-visit points, and maximum route duration.
- Personalize dwell time when possible: food, coffee, photo spots, parks, museums, family/senior context, and user interest should affect stay duration.

### Validation / Repair

Validate every route before presentation:

- All POIs exist in the data source.
- Arrival times fit opening hours when available.
- Total duration fits the time window.
- Strict budget is not exceeded.
- Required categories and must-visit POIs are covered.
- Queue, walking, and travel distances do not violate hard limits.
- Explanation facts are consistent with route stops and score evidence.

Repair at most a bounded number of times. Common repairs: replace closed POI, replace expensive POI, replace high-queue POI, remove low-priority stop, reorder stops, insert required category, compress dwell time, or switch outdoor stops to indoor.

### Replanning

Classify events before changing the route:

- Minor replan: replace one POI for "少排队", "换一家", "太贵", or one rejected stop.
- Partial replan: preserve completed/current stops and replan remaining stops for rain, delay, user location drift, or reduced remaining time.
- Full replan: re-enter onboarding/understanding when destination, time budget, party type, or trip goal changes substantially.

Always revalidate the updated route and preserve route history/version context.

### Explanation / Chat

- Explain tradeoffs plainly: why this route, why dropped POIs, where risk remains, and what changed after replanning.
- Offer user control in negative or failure scenarios: alternatives, retry, narrower constraints, or human/manual fallback wording.
- Never claim a deal, opening status, queue time, or price unless it exists in data or is clearly marked as mock/estimated.

## Frontend Expectations

- The first screen should be the usable trip creation/planning flow, not a marketing page.
- Route result pages should show summary, timeline, POI cards, UGC evidence, validation status, risk warnings, map/sequence, alternatives, and replan controls.
- Replan controls should be concrete actions such as 少排队, 更省钱, 少走路, 雨天室内, 亲子友好, 老人友好, 压缩到 2 小时, 增加咖啡休息点.
- Keep mobile text and buttons stable; do not let long labels overflow route cards or timeline items.

## Tests

Add or update tests for the changed stage:

- Onboarding: missing slots, completeness score, budget/time/party parsing, avoid/style mapping.
- Candidate pool: fallback retrieval, provenance, UGC evidence, selected POI preservation.
- Scoring: queue, price, distance, UGC, context, and party-type weights.
- Optimization: time window, start/end, required categories, must-visit, dropped POI reasons.
- Validation/repair: closed POI, over-budget, overtime, high queue, missing category, outdoor-to-indoor repair.
- Replanning: minor replacement lowers queue/cost, partial replan preserves completed stops, compressed route fits target time.
- Explanation: no nonexistent POIs, no unsupported claims, reasons match score/UGC/attributes.

## Anti-Patterns

- Do not add a second route planner if `SolverService`, `PlanService`, or `RouteReplanner` can be extended.
- Do not hide validation failures behind polished copy.
- Do not use UGC popularity alone as personalization.
- Do not treat "recommended POIs" as an already valid itinerary.
- Do not make the frontend wait for long AI explanations before showing the route.
- Do not remove existing fallback behavior; this demo must work without external APIs.

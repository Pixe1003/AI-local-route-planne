---
name: need-profile-agent
description: AIroute need profile guide. Use when working on user need parsing, profile schemas, prompt/time/budget/preference extraction, or UGC-first route request inputs.
---

# Need Profile Agent

## Purpose

This skill turns natural language and lightweight UI inputs into `UserNeedProfile`. In the current frontend, need capture happens inside `DiscoveryFeedPage.tsx`, then feeds POI recommendation and Amap route generation.

Use `../local-route-agent/references/paper-insights.md` for shared research rationale.

## Owns

- Backend: `backend/app/services/onboarding_service.py`
- Schemas: `backend/app/schemas/onboarding.py`
- APIs: `backend/app/api/routes_onboarding.py`
- Frontend: `frontend/src/pages/DiscoveryFeedPage.tsx`, `frontend/src/types/onboarding.ts`, `frontend/src/store/userStore.ts`

## Rules

- Do not invent exact locations, strict budgets, or time windows. Use explicit defaults only when the UI makes them visible.
- Store uncertainty as missing or weak confidence instead of turning it into a fake fact.
- Map user language into constraints such as low queue, low walking, indoor preference, budget per person, local food, photo spots, or category blacklist.
- Keep fields machine-usable and put long text in `raw_query`.
- Do not produce POIs or route geometry during need profiling.

## Tests

Cover missing start/time/party/budget/preference slots, Chinese time and budget parsing, explicit answer precedence, and no hallucinated POIs or routes.

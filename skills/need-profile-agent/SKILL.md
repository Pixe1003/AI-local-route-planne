---
name: need-profile-agent
description: AIroute Need Profile Agent 的开发、修改、评审和测试指南。Use when working on onboarding, slot filling, user need profiling, completeness scoring, follow-up questions, party/time/budget/preference parsing, UserNeedProfile schemas, or TripCreatePage need collection.
---

# Need Profile Agent

## Purpose

Use this skill to make AIroute understand what the user wants before route planning starts. This Agent turns natural language, quick tags, and form answers into a structured `UserNeedProfile` and decides whether the system can plan or should ask follow-up questions.

Use `../local-route-agent/references/paper-insights.md` for the shared research rationale. Keep this skill focused on need capture and profile quality.

## Owns

- Backend: `backend/app/services/onboarding_service.py`, `profile_service.py`
- Schemas: `backend/app/schemas/onboarding.py`
- APIs: `backend/app/api/routes_onboarding.py`
- Frontend: `frontend/src/pages/TripCreatePage.tsx`, `frontend/src/api/onboarding.ts`, `frontend/src/types/onboarding.ts`, `frontend/src/store/userStore.ts`

## Inputs And Outputs

Input sources:

- Natural-language trip request
- Quick tags for style, party, food, activity, budget, and weather
- Explicit form answers
- Existing trip/user context when available

Output:

- `UserNeedProfile`
- completeness score
- missing slot list
- follow-up questions
- `can_plan` and `should_ask_followup`

## Workflow

1. Extract slots from user text and UI selections.
2. Normalize values into stable schema fields.
3. Merge explicit answers over inferred values.
4. Score completeness.
5. Ask only for missing high-value slots when score is too low.
6. Produce a profile that downstream Agents can use without guessing.

## Rules

- Required planning slots are city/start area, time budget or time window, at least one food/activity preference, party type, and budget or budget tolerance.
- Do not invent exact locations, strict budgets, or time windows. Ask or use explicit defaults marked as defaults.
- Store uncertainty as missing/weak confidence instead of turning it into a fake fact.
- Map natural language into constraints: "不想排队" -> low queue / avoid long queue; "怕累" or "带老人" -> low walking; "下雨" -> indoor preferred; "人均 150" -> budget per person.
- Party type affects later weights: senior/family increases low walking, rest, safety, seating, indoor; couple increases atmosphere/photo/night view; friends increases food, interaction, entertainment.
- Keep profile fields small and machine-usable. Put long natural-language text in `raw_query` or notes.

## Tests

Cover:

- Missing start location, time, party, budget, and preference slots.
- Completeness thresholds around `0.5` and `0.8`.
- Parsing of Chinese time, budget, party type, avoid items, route style, rain, and low walking.
- Explicit answer merge overriding inferred values.
- No hallucinated POIs or routes during onboarding.

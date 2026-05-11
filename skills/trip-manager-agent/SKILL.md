---
name: trip-manager-agent
description: AIroute legacy trip compatibility guide. Use only when working on retained backend trip APIs, route version records, or migration away from in-memory trip state.
---

# Trip Manager Agent

## Purpose

Trip persistence is no longer part of the current frontend product flow. The backend `/api/trips/*` APIs remain for compatibility and tests until a future persistence design replaces them.

Use `../local-route-agent/references/paper-insights.md` for shared research rationale.

## Owns

- Backend: `backend/app/services/trip_service.py`, `state.py`
- APIs: `backend/app/api/routes_trips.py`
- Schemas: `backend/app/schemas/trip.py`, legacy route-version fields in `plan.py`

## Rules

- Do not reintroduce trip pages or trip stores into the current frontend without a new product decision.
- Keep route versions immutable if backend compatibility code is changed.
- Preserve enough structured route data for legacy tests to restore a trip record.
- Prefer a future persistence migration over expanding in-memory registries.

## Tests

Cover listing trip summaries, saving a first route version, appending a route version, restoring trip detail, active version selection, and local fallback behavior.

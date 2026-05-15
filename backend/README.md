# Backend

FastAPI backend for the local route agent. The current default city is Hefei, with POI and UGC inputs loaded from local processed data:

- `data/processed/hefei_pois.sqlite` for structured POI search and recommendation pools.
- `data/processed/ugc_hefei.jsonl` for UGC cold-start and evidence retrieval.
- LongCat is configured through the OpenAI-compatible endpoint `https://api.longcat.ai/v1` with model `longcat-max`.
- Agent tool-calling is enabled by default; tests can still force deterministic fallback mode with environment overrides.

Run locally:

```bash
python -m pip install -e .[dev]
python -m pytest tests -q
python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

The legacy Shanghai seed data remains in the repository for older harnesses and fixtures, but the live agent path should not silently fall back to Shanghai when Hefei has no selected POIs.

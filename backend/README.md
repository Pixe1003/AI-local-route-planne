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

Product-demo RAG path:

```bash
python ../scripts/build_faiss_rag.py --city hefei --sqlite-path ../data/processed/hefei_pois.sqlite --require-real-data --index-dir ../data/faiss
curl http://127.0.0.1:8000/health
```

`/health` reports `rag`, `faiss`, `amap`, `cache`, and `memory` subsystem status. A missing Amap key should degrade transport to haversine fallback without blocking route generation. A missing real SQLite file should fail the FAISS build when `--require-real-data` is set, so seed fallback is not mistaken for product RAG readiness.

Origin-aware pool requests can include `origin_latitude`, `origin_longitude`, and `radius_meters`. Returned pool POIs include `distance_meters`, retrieval provenance, and evidence snippets for frontend route cards.

The legacy Shanghai seed data remains in the repository for older harnesses and fixtures, but the live agent path should not silently fall back to Shanghai when Hefei has no selected POIs.

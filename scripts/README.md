# Scripts

Run scripts from the project root.

## `import_hefei_pois.py`

Imports raw Hefei POI data into `data/processed/hefei_pois.sqlite`.

```powershell
python scripts/import_hefei_pois.py
```

## Retrieval indexes

Generate deterministic Hefei demo UGC from the local POI SQLite. The output is
`data/processed/ugc_hefei.jsonl`, uses `source=simulated_ugc`, and is ignored by
git because it is a local demo data artifact:

```powershell
python scripts/generate_demo_ugc.py
```

Build the SQLite retrieval tables used by candidate recall and UGC evidence lookup:

```powershell
python scripts/build_retrieval_index.py
```

Build the unified POI/UGC FAISS RAG index with `BAAI/bge-small-zh-v1.5`:

```powershell
python scripts/build_faiss_rag.py --city hefei --index-dir data\faiss
```

For slower networks, set a Hugging Face mirror before running:

```powershell
$env:HF_ENDPOINT='https://hf-mirror.com'
python scripts/build_faiss_rag.py --city hefei --index-dir data\faiss
```

Generated model and index artifacts such as `data/models/ranker.txt`,
`data/eval/ranker_train.json`, and `data/faiss/*` are local demo assets and
should not be committed.

## `replay_trace.py`

Reads a persisted agent session from SQLite and prints the tool trace.

```powershell
python scripts/replay_trace.py {session_id}
```

## `train_ranker.py`

Trains the POI learning-to-rank model (LightGBM LambdaMART) over a set of
synthesized queries that exercise the live `PoiScoringService`, so training
features stay aligned with serving features.

```powershell
python scripts/train_ranker.py --city hefei
```

Outputs:

- `data/models/ranker.txt` — the trained Booster.
- `data/eval/ranker_train.json` — training rows, validation rows,
  `model_ndcg_at_5`, `baseline_ndcg_at_5`, `ranker_enabled_recommended`.

Inference is gated by `ranker_enabled` (default `True`). The serving path
(`PoiScoringService._ranker_score` → `PoiRanker.predict`) returns `None` when
the model file is missing, so `total` automatically falls back to the
rule-based sum. In other words: enabling the flag without a model file is
safe; once the file exists the ranker activates without a restart.

Recommended workflow:

1. Run training, inspect `data/eval/ranker_train.json`.
2. Keep `ranker_enabled=True` only if `ranker_enabled_recommended` is `true`
   (i.e. the model beats the rule baseline NDCG@5 by ≥ 3%); otherwise set it
   to `false` via `.env` until training improves.

## `bench_latency.py`

Measures `/api/agent/run` response latency under a 2 × N × 5 matrix:

- 2 decision modes: `rule` (fast path) vs `llm` (function calling).
- N repeats per scenario; first repeat is the cold call, the rest are warm.
- 5 scenarios from `backend/eval/scenarios/`.

Outputs a markdown report to `data/eval/latency_report.md` containing:

- E2E p50 / p95 / p99 / min / max / mean (warm, all scenarios pooled)
- Cold-start latency per (scenario, mode)
- Per-scenario E2E (warm)
- Per-tool latency breakdown (warm only)
- Advisory, non-gating thresholds:
  - warm p95 <= 4500 ms
  - max cold <= warm p95 x 3

```powershell
# default: rule + llm, 5 repeats, ~5 × 2 × 5 = 50 calls
python scripts\bench_latency.py

# quick smoke
python scripts\bench_latency.py --repeats 2

# only one mode
python scripts\bench_latency.py --modes rule --repeats 3

# serious tail-latency measurement
python scripts\bench_latency.py --repeats 30
```

Amap is stubbed (same patch as `backend/eval/run_eval.py`) so reported timings
reflect the Agent + solver critical path, not network jitter. See
`docs/响应速度测试设计.md` for variable matrix, metric definitions, and known
caveats. When `--repeats` is below 20, the generated report labels p99 as a
weak exploratory signal instead of a tail-latency commitment.

## `warmup_demo_sessions.py`

Posts several demo `/api/agent/run` requests for `demo_user` so user facts and similar-session memory have content for demos. Start the backend first.

```powershell
python scripts/warmup_demo_sessions.py
```

To target a non-default backend URL:

```powershell
$env:AIROUTE_API_BASE_URL='http://127.0.0.1:8000'
python scripts/warmup_demo_sessions.py
```

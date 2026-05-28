# Scripts

Run scripts from the project root.

## `import_hefei_pois.py`

Imports raw Hefei POI data into `data/processed/hefei_pois.sqlite`.

```powershell
python scripts/import_hefei_pois.py
```

## Retrieval indexes

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

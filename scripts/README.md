# Scripts

Run scripts from the project root.

## `import_hefei_pois.py`

Imports raw Hefei POI data into `data/processed/hefei_pois.sqlite`.

```powershell
python scripts/import_hefei_pois.py
```

## `embed_ugc.py`

Encodes `data/processed/ugc_hefei.jsonl` with `BAAI/bge-small-zh-v1.5` and writes:

- `data/processed/ugc_hefei.faiss`
- `data/processed/ugc_hefei_embeddings.npy`
- `data/processed/ugc_hefei_meta.jsonl`

```powershell
python scripts/embed_ugc.py
```

For slower networks, set a Hugging Face mirror before running:

```powershell
$env:HF_ENDPOINT='https://hf-mirror.com'
python scripts/embed_ugc.py
```

## `replay_trace.py`

Reads a persisted agent session from SQLite and prints the tool trace.

```powershell
python scripts/replay_trace.py {session_id}
```

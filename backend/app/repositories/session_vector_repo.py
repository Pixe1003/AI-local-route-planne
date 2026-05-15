import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.agent.state import AgentState
from app.observability.metrics import CACHE_HIT_RATE
from app.repositories import embedding_cache
from app.schemas.user_memory import SessionSummary, SimilarSessionHit


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODEL_NAME = "BAAI/bge-small-zh-v1.5"


class SessionVectorRepo:
    def __init__(self, sessions_dir: str | Path | None = None) -> None:
        self._dir = Path(sessions_dir or PROJECT_ROOT / "data" / "processed" / "sessions")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._indexes: dict[str, Any] = {}
        self._metas: dict[str, list[dict[str, Any]]] = {}
        self._model: Any | None = None
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def add_session(self, state: AgentState, summary: SessionSummary) -> None:
        vector = self._encode(self._session_to_text(summary))
        if vector is None:
            return
        vector = _as_2d_float32(vector)
        if vector is None:
            return

        with self._user_lock(state.goal.user_id):
            index, metas = self._get_or_create_index(state.goal.user_id, dim=vector.shape[1])
            if any(meta.get("session_id") == state.goal.session_id for meta in metas):
                return
            index.add(vector)
            metas.append(
                {
                    "session_id": state.goal.session_id,
                    "user_id": state.goal.user_id,
                    "raw_query": summary.raw_query,
                    "theme": summary.theme,
                    "stop_poi_names": summary.stop_poi_names,
                    "created_at": summary.created_at.isoformat(),
                }
            )
            self._persist(state.goal.user_id, index, metas)

    def search_similar(
        self,
        user_id: str,
        query: str,
        *,
        top_k: int = 3,
        exclude_session_id: str | None = None,
    ) -> list[SimilarSessionHit]:
        if not query.strip() or top_k <= 0:
            return []
        loaded = self._load_user_index(user_id)
        if loaded is None:
            return []
        index, metas = loaded
        if not metas or int(index.ntotal) <= 0:
            return []

        vector = self._encode(query)
        vector = _as_2d_float32(vector) if vector is not None else None
        if vector is None or vector.shape[1] != index.d:
            return []

        search_k = min(int(index.ntotal), max(top_k * 3, top_k))
        scores, indices = index.search(vector, search_k)
        now = datetime.now(timezone.utc)
        hits: list[SimilarSessionHit] = []
        for score, raw_idx in zip(scores[0], indices[0]):
            idx = int(raw_idx)
            if idx < 0 or idx >= len(metas):
                continue
            meta = metas[idx]
            if exclude_session_id and meta.get("session_id") == exclude_session_id:
                continue
            hits.append(
                SimilarSessionHit(
                    session_id=str(meta.get("session_id") or ""),
                    raw_query=str(meta.get("raw_query") or ""),
                    theme=meta.get("theme"),
                    similarity=round(float(score), 4),
                    stop_poi_names=[
                        str(item) for item in meta.get("stop_poi_names", []) if item
                    ],
                    days_ago=max(0, (now - _parse_datetime(meta.get("created_at"))).days),
                )
            )
            if len(hits) >= top_k:
                break
        return hits

    def _session_to_text(self, summary: SessionSummary) -> str:
        return " | ".join(
            item
            for item in [
                summary.raw_query,
                summary.theme or "",
                summary.narrative or "",
                " ".join(summary.stop_poi_names),
            ]
            if item
        )

    def _user_lock(self, user_id: str) -> threading.Lock:
        with self._locks_guard:
            if user_id not in self._locks:
                self._locks[user_id] = threading.Lock()
            return self._locks[user_id]

    def _encode(self, text: str):
        key = embedding_cache.cache_key(MODEL_NAME, text)
        cached = embedding_cache.get(key)
        if cached is not None:
            CACHE_HIT_RATE.labels(cache_name="embedding_query", result="hit").inc()
            return cached
        CACHE_HIT_RATE.labels(cache_name="embedding_query", result="miss").inc()
        try:
            import numpy as np
            from sentence_transformers import SentenceTransformer
        except ImportError:
            return None
        try:
            if self._model is None:
                self._model = SentenceTransformer(MODEL_NAME, local_files_only=True)
            embedding = np.asarray(self._model.encode(text, normalize_embeddings=True), dtype="float32")
            embedding_cache.put(key, embedding)
            return embedding
        except Exception:
            return None

    def _get_or_create_index(self, user_id: str, *, dim: int):
        loaded = self._load_user_index(user_id)
        if loaded is not None:
            return loaded
        try:
            import faiss
        except ImportError:
            index = _NumpyFlatIPIndex(dim)
            self._indexes[user_id] = index
            self._metas[user_id] = []
            return index, self._metas[user_id]
        index = faiss.IndexFlatIP(dim)
        self._indexes[user_id] = index
        self._metas[user_id] = []
        return index, self._metas[user_id]

    def _load_user_index(self, user_id: str):
        if user_id in self._indexes and user_id in self._metas:
            return self._indexes[user_id], self._metas[user_id]
        index_path, meta_path = self._paths(user_id)
        if not index_path.exists() or not meta_path.exists():
            return None
        metas = [
            json.loads(line)
            for line in meta_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        try:
            import faiss
        except ImportError:
            index = _NumpyFlatIPIndex.load(index_path)
            if index is None:
                return None
        else:
            try:
                index = faiss.read_index(str(index_path))
            except Exception:
                index = _NumpyFlatIPIndex.load(index_path)
                if index is None:
                    return None
        if int(index.ntotal) != len(metas):
            return None
        self._indexes[user_id] = index
        self._metas[user_id] = metas
        return index, metas

    def _persist(self, user_id: str, index, metas: list[dict[str, Any]]) -> None:
        index_path, meta_path = self._paths(user_id)
        try:
            import faiss
        except ImportError:
            if hasattr(index, "save"):
                index.save(index_path)
            else:
                return
        else:
            try:
                faiss.write_index(index, str(index_path))
            except Exception:
                if hasattr(index, "save"):
                    index.save(index_path)
                else:
                    return
        try:
            meta_path.write_text(
                "\n".join(json.dumps(meta, ensure_ascii=False) for meta in metas),
                encoding="utf-8",
            )
        except Exception:
            return

    def _paths(self, user_id: str) -> tuple[Path, Path]:
        name = _safe_user_file_stem(user_id)
        return self._dir / f"{name}.faiss", self._dir / f"{name}.meta.jsonl"


@lru_cache
def get_session_vector_repo() -> SessionVectorRepo:
    return SessionVectorRepo()


def _safe_user_file_stem(user_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", user_id).strip("._") or "user"
    if cleaned == user_id:
        return cleaned
    digest = hashlib.sha1(user_id.encode("utf-8")).hexdigest()[:8]
    return f"{cleaned}_{digest}"


def _as_2d_float32(vector):
    try:
        import numpy as np

        arr = np.asarray(vector, dtype="float32")
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        if arr.ndim != 2 or arr.shape[1] <= 0:
            return None
        return arr
    except Exception:
        return None


def _parse_datetime(raw: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class _NumpyFlatIPIndex:
    def __init__(self, dim: int, vectors=None) -> None:
        import numpy as np

        self.d = dim
        self._vectors = (
            np.asarray(vectors, dtype="float32").reshape(-1, dim)
            if vectors is not None
            else np.empty((0, dim), dtype="float32")
        )

    @property
    def ntotal(self) -> int:
        return int(self._vectors.shape[0])

    def add(self, vector) -> None:
        import numpy as np

        arr = np.asarray(vector, dtype="float32")
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        if arr.shape[1] != self.d:
            return
        self._vectors = np.vstack([self._vectors, arr])

    def search(self, vector, top_k: int):
        import numpy as np

        arr = np.asarray(vector, dtype="float32")
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        if self.ntotal == 0 or arr.shape[1] != self.d:
            return (
                np.asarray([[]], dtype="float32"),
                np.asarray([[]], dtype="int64"),
            )
        scores = self._vectors @ arr[0]
        order = np.argsort(-scores)[:top_k]
        return scores[order].reshape(1, -1), order.reshape(1, -1)

    def save(self, path: Path) -> None:
        path.write_text(
            json.dumps({"dim": self.d, "vectors": self._vectors.tolist()}),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(int(data["dim"]), data.get("vectors", []))
        except Exception:
            return None

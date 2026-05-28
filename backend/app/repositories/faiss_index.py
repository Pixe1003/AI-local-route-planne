from pathlib import Path
from typing import Any, cast

import numpy as np

from app.llm.embedding import Embedder, EmbeddingUnavailable, SentenceTransformerEmbedder
from app.repositories.faiss_meta import FaissMetaStore
from app.repositories.rag_build import resolve_faiss_paths


class FaissVectorIndex:
    def __init__(self, path: str | Path, *, embedder: Embedder | None = None, oversample: int = 8) -> None:
        self.index_path, self.meta_path = resolve_faiss_paths(path)
        self.embedder = embedder or SentenceTransformerEmbedder()
        self.oversample = max(1, oversample)
        self._index: Any | None = None
        self._meta_rows: list[dict[str, Any]] | None = None

    def exists(self) -> bool:
        return self.index_path.exists() and self.meta_path.exists()

    def count(self) -> int:
        return len(self._load_meta_rows()) if self.meta_path.exists() else 0

    def query(
        self,
        *,
        text: str,
        city: str,
        top_k: int,
        category_filters: list[str] | None = None,
        source_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if top_k <= 0 or not text.strip() or not self.exists():
            return []
        index = self._load_index()
        metas = self._load_meta_rows()
        if not metas or int(index.ntotal) == 0:
            return []

        query_vector = np.asarray(self.embedder.embed_query(text), dtype="float32")
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)
        query_vector = _normalize_rows(query_vector)

        search_k = min(int(index.ntotal), max(top_k * self.oversample, top_k))
        scores, indices = index.search(query_vector, search_k)
        rows: list[dict[str, Any]] = []
        allowed_categories = set(category_filters or [])
        allowed_sources = set(source_types or [])
        for score, faiss_id in zip(scores[0], indices[0]):
            faiss_id = int(faiss_id)
            if faiss_id < 0 or faiss_id >= len(metas):
                continue
            meta = metas[faiss_id]
            metadata = dict(meta.get("metadata") or {})
            if city and metadata.get("city") != city:
                continue
            if allowed_categories and metadata.get("category") not in allowed_categories:
                continue
            source_type = str(metadata.get("source_type") or meta.get("source_type") or "poi_profile")
            if allowed_sources and source_type not in allowed_sources:
                continue
            rows.append(
                {
                    "poi_id": str(meta.get("poi_id") or metadata.get("poi_id") or ""),
                    "score": float(score),
                    "doc_id": str(meta.get("doc_id") or ""),
                    "source_type": source_type,
                    "text": str(meta.get("text") or ""),
                    "metadata": metadata,
                }
            )
            if len(rows) >= top_k:
                break
        return rows

    def _load_index(self):
        if self._index is not None:
            return self._index
        if not self.index_path.exists():
            raise EmbeddingUnavailable("FAISS index does not exist")
        try:
            import faiss
        except ImportError as exc:
            raise EmbeddingUnavailable("faiss is not installed") from exc
        self._index = faiss.read_index(str(self.index_path))
        return self._index

    def _load_meta_rows(self) -> list[dict[str, Any]]:
        if self._meta_rows is None:
            self._meta_rows = FaissMetaStore(self.meta_path).read()
        return self._meta_rows


def _normalize_rows(values: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return cast(np.ndarray, values / norms)

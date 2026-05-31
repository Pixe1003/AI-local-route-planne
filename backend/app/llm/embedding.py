from functools import lru_cache
from typing import Protocol

import numpy as np

from app.config import get_settings
from app.observability.metrics import CACHE_HIT_RATE
from app.repositories import embedding_cache


class EmbeddingUnavailable(RuntimeError):
    pass


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]): ...

    def embed_query(self, text: str): ...


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or get_settings().embedding_model
        self._model = None

    def embed_documents(self, texts: list[str]):
        if not texts:
            return np.empty((0, 0), dtype="float32")
        return np.asarray(
            self._model_instance().encode(texts, normalize_embeddings=True),
            dtype="float32",
        )

    def embed_query(self, text: str):
        key = embedding_cache.cache_key(self.model_name, text)
        cached = embedding_cache.get(key)
        if cached is not None:
            CACHE_HIT_RATE.labels(cache_name="embedding_query", result="hit").inc()
            return cached
        CACHE_HIT_RATE.labels(cache_name="embedding_query", result="miss").inc()
        embedding = np.asarray(
            self._model_instance().encode(text, normalize_embeddings=True),
            dtype="float32",
        )
        embedding_cache.put(key, embedding)
        return embedding

    def _model_instance(self):
        if self._model is not None:
            return self._model
        self._model = get_sentence_transformer_model(self.model_name)
        return self._model


@lru_cache(maxsize=4)
def get_sentence_transformer_model(model_name: str):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise EmbeddingUnavailable("sentence-transformers is not installed") from exc
    try:
        return SentenceTransformer(model_name)
    except Exception as exc:
        raise EmbeddingUnavailable("embedding model is unavailable") from exc

from collections import OrderedDict
import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingUnavailable(RuntimeError):
    pass


class EmbeddingClient:
    """OpenAI-compatible embedding boundary used by the RAG index."""

    _query_cache: "OrderedDict[tuple[str, str], list[float]]" = OrderedDict()
    _QUERY_CACHE_MAX = 512

    @classmethod
    def clear_query_cache(cls) -> None:
        cls._query_cache.clear()

    def embed_query(self, text: str) -> list[float]:
        settings = get_settings()
        key = (settings.embedding_model, text)
        cached = self._query_cache.get(key)
        if cached is not None:
            self._query_cache.move_to_end(key)
            return cached
        vector = self.embed_texts([text])[0]
        self._query_cache[key] = vector
        self._query_cache.move_to_end(key)
        if len(self._query_cache) > self._QUERY_CACHE_MAX:
            self._query_cache.popitem(last=False)
        return vector

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        settings = get_settings()
        if not settings.embedding_api_key:
            logger.info("Embedding unavailable: no api key configured")
            raise EmbeddingUnavailable("embedding API key is not configured")
        base_url = settings.embedding_base_url or settings.llm_base_url or "https://api.openai.com/v1"
        try:
            response = httpx.post(
                f"{base_url.rstrip('/')}/embeddings",
                headers={
                    "Authorization": f"Bearer {settings.embedding_api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": settings.embedding_model, "input": texts},
                timeout=settings.embedding_timeout_seconds,
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            data = payload.get("data", [])
            vectors = [item.get("embedding") for item in data]
            if len(vectors) != len(texts) or not all(isinstance(vector, list) for vector in vectors):
                raise EmbeddingUnavailable("embedding response shape is invalid")
            return vectors
        except Exception as exc:
            if isinstance(exc, EmbeddingUnavailable):
                raise
            logger.warning("Embedding call failed: %s", exc)
            raise EmbeddingUnavailable(str(exc)) from exc

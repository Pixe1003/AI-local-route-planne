import hashlib
from typing import Any

from app.cache_backend import InMemoryLRUBackend


_CACHE = InMemoryLRUBackend(maxsize=500)


def cache_key(model_name: str, text: str) -> str:
    return hashlib.md5(f"{model_name}|{text}".encode("utf-8")).hexdigest()


def get(key: str) -> Any | None:
    return _CACHE.get(key)


def put(key: str, embedding: Any) -> None:
    _CACHE.set(key, embedding)


def clear() -> None:
    _CACHE.clear()

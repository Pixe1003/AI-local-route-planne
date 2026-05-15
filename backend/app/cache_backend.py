"""Small cache backend abstractions for local caches and future Redis migration."""

from __future__ import annotations

from threading import Lock
from typing import Any, Protocol

from cachetools import LRUCache, TTLCache


class CacheBackend(Protocol):
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl: int | None = None) -> None: ...
    def delete(self, key: str) -> None: ...
    def clear(self) -> None: ...


class InMemoryTTLBackend:
    def __init__(self, *, maxsize: int = 1000, default_ttl: int = 300) -> None:
        self._cache: TTLCache[str, Any] = TTLCache(maxsize=maxsize, ttl=default_ttl)
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            return self._cache.get(key)

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        with self._lock:
            self._cache[key] = value

    def delete(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


class InMemoryLRUBackend:
    def __init__(self, *, maxsize: int = 500) -> None:
        self._cache: LRUCache[str, Any] = LRUCache(maxsize=maxsize)
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            return self._cache.get(key)

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        with self._lock:
            self._cache[key] = value

    def delete(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


class RedisBackend:
    def __init__(self, url: str) -> None:
        import redis

        self._client = redis.from_url(url, decode_responses=False)

    def get(self, key: str) -> Any | None:
        import pickle

        raw = self._client.get(key)
        return pickle.loads(raw) if raw is not None else None

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        import pickle

        self._client.set(key, pickle.dumps(value), ex=ttl)

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def clear(self) -> None:
        raise NotImplementedError("RedisBackend.clear requires an explicit key namespace")

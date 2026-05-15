import copy
import hashlib
import json
from typing import Any

from app.cache_backend import InMemoryTTLBackend


_CACHE = InMemoryTTLBackend(maxsize=2000, default_ttl=300)


def cache_key(
    prompt: str,
    tools: list[dict[str, Any]] | None = None,
    system_prompt: str | None = None,
    *,
    model: str | None = None,
) -> str:
    payload = json.dumps(
        {
            "prompt": prompt,
            "system_prompt": system_prompt,
            "tools": [tool.get("name") for tool in tools or []],
            "model": model,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get(key: str) -> dict[str, Any] | None:
    value = _CACHE.get(key)
    return copy.deepcopy(value) if isinstance(value, dict) else None


def put(key: str, value: dict[str, Any]) -> None:
    _CACHE.set(key, copy.deepcopy(value))


def clear() -> None:
    _CACHE.clear()

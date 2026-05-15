import json
from collections import defaultdict
from typing import Any


_EVENTS: dict[str, list[dict[str, Any]]] = defaultdict(list)


def reset_trace(session_id: str) -> None:
    _EVENTS[session_id] = []


def record_event(session_id: str, event: dict[str, Any]) -> None:
    _EVENTS[session_id].append(event)


def get_trace_events(session_id: str) -> list[dict[str, Any]]:
    return list(_EVENTS.get(session_id, []))


def format_sse(events: list[dict[str, Any]]) -> str:
    return "".join(f"data: {json.dumps(event, ensure_ascii=False)}\n\n" for event in events)

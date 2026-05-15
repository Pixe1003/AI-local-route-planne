import asyncio
import json
from collections import defaultdict
from typing import Any


_EVENTS: dict[str, list[dict[str, Any]]] = defaultdict(list)
_QUEUES: dict[str, list[asyncio.Queue]] = defaultdict(list)
_QUEUE_LOOPS: dict[asyncio.Queue, asyncio.AbstractEventLoop] = {}


def reset_trace(session_id: str) -> None:
    _EVENTS[session_id] = []


def record_event(session_id: str, event: dict[str, Any]) -> None:
    _EVENTS[session_id].append(event)
    for queue in list(_QUEUES.get(session_id, [])):
        loop = _QUEUE_LOOPS.get(queue)
        if loop and loop.is_running():
            loop.call_soon_threadsafe(queue.put_nowait, event)
        else:
            queue.put_nowait(event)


def get_trace_events(session_id: str) -> list[dict[str, Any]]:
    return list(_EVENTS.get(session_id, []))


def format_sse(events: list[dict[str, Any]]) -> str:
    return "".join(f"data: {json.dumps(event, ensure_ascii=False)}\n\n" for event in events)


def subscribe(session_id: str) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue()
    _QUEUES[session_id].append(queue)
    try:
        _QUEUE_LOOPS[queue] = asyncio.get_running_loop()
    except RuntimeError:
        pass
    return queue


def unsubscribe(session_id: str, queue: asyncio.Queue) -> None:
    queues = _QUEUES.get(session_id, [])
    if queue in queues:
        queues.remove(queue)
    _QUEUE_LOOPS.pop(queue, None)
    if not queues and session_id in _QUEUES:
        del _QUEUES[session_id]

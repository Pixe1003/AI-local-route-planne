import asyncio

from app.agent.tracing import record_event, reset_trace, subscribe, unsubscribe


def test_trace_subscriber_receives_incremental_events() -> None:
    async def run() -> dict:
        session_id = "trace_stream_test"
        reset_trace(session_id)
        queue = subscribe(session_id)
        try:
            event = {"type": "observed", "tool": "parse_intent"}
            record_event(session_id, event)
            return await asyncio.wait_for(queue.get(), timeout=1)
        finally:
            unsubscribe(session_id, queue)

    assert asyncio.run(run()) == {"type": "observed", "tool": "parse_intent"}

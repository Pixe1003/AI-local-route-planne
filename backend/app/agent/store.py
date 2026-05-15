import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from app.agent.state import AgentState


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = PROJECT_ROOT / "data" / "processed" / "agent_sessions.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    phase TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON agent_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON agent_sessions(updated_at DESC);

CREATE TABLE IF NOT EXISTS user_facts (
    user_id TEXT PRIMARY KEY,
    facts_json TEXT NOT NULL,
    session_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_updated ON user_facts(updated_at DESC);
"""


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_SCHEMA)
    return conn


def save_state(state: AgentState) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO agent_sessions
                (session_id, user_id, kind, phase, trace_id, state_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                user_id = excluded.user_id,
                kind = excluded.kind,
                phase = excluded.phase,
                trace_id = excluded.trace_id,
                state_json = excluded.state_json,
                updated_at = excluded.updated_at
            """,
            (
                state.goal.session_id,
                state.goal.user_id,
                state.goal.kind,
                state.phase,
                state.trace_id,
                state.model_dump_json(),
                now,
                now,
            ),
        )
    _invalidate_user_facts(state.goal.user_id)
    _queue_session_vector_persist(state)


def load_state(session_id: str) -> AgentState | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT state_json FROM agent_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return AgentState.model_validate_json(row[0]) if row else None


def list_sessions(user_id: str, limit: int = 20) -> list[AgentState]:
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT state_json FROM agent_sessions
            WHERE user_id = ?
            ORDER BY updated_at DESC, created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return [AgentState.model_validate_json(row[0]) for row in rows]


def session_cost_summary(session_id: str) -> dict[str, Any]:
    state = load_state(session_id)
    if state is None:
        return {}
    total_tokens = sum(step.tokens_used for step in state.steps)
    total_latency = sum(step.latency_ms for step in state.steps)
    return {
        "session_id": session_id,
        "total_tokens": total_tokens,
        "total_latency_ms": total_latency,
        "tool_count": len(state.steps),
        "tools_by_latency": sorted(
            [{"name": step.tool_name, "ms": step.latency_ms} for step in state.steps],
            key=lambda item: -cast(int, item["ms"]),
        )[:5],
        "estimated_cost_usd": round(total_tokens * 0.0000002, 6),
    }


def _invalidate_user_facts(user_id: str) -> None:
    try:
        from app.agent.user_memory import invalidate_facts

        invalidate_facts(user_id)
    except Exception:
        return


def _persist_session_vector(state: AgentState) -> None:
    if state.phase != "DONE" or state.memory.story_plan is None:
        return
    try:
        from app.agent.session_summarizer import summarize_session
        from app.repositories.session_vector_repo import get_session_vector_repo

        get_session_vector_repo().add_session(state, summarize_session(state))
    except Exception:
        return


def _queue_session_vector_persist(state: AgentState) -> None:
    if state.phase != "DONE" or state.memory.story_plan is None:
        return
    snapshot = state.model_copy(deep=True)
    thread = threading.Thread(
        target=_persist_session_vector,
        args=(snapshot,),
        name=f"session-vector-{state.goal.session_id[:8]}",
        daemon=True,
    )
    thread.start()

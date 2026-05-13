import sqlite3
from datetime import datetime, timezone
from pathlib import Path

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

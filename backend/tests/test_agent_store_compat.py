import json

from app.agent import store
from app.agent.state import AgentGoal, AgentState
from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import PlanContext
from app.schemas.pool import TimeWindow


def _state(session_id: str) -> AgentState:
    context = PlanContext(
        city="hefei",
        date="2026-05-28",
        time_window=TimeWindow(start="10:00", end="18:00"),
        party="friends",
        budget_per_person=120,
    )
    return AgentState(
        goal=AgentGoal(raw_query="route", session_id=session_id, user_id="legacy_user"),
        profile=UserNeedProfile.from_plan_context(context, raw_query="route"),
        context=context,
    )


def test_list_sessions_skips_legacy_states_that_no_longer_validate(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "agent_sessions.sqlite", raising=False)
    monkeypatch.setattr(store, "_queue_session_vector_persist", lambda state: None, raising=False)
    store.save_state(_state("valid"))

    with store._conn() as conn:
        conn.execute(
            """
            INSERT INTO agent_sessions
                (session_id, user_id, kind, phase, trace_id, state_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                "legacy",
                "legacy_user",
                "plan_route",
                "DONE",
                "trace",
                json.dumps({"legacy": "missing required AgentState fields"}),
            ),
        )

    assert [state.goal.session_id for state in store.list_sessions("legacy_user")] == ["valid"]
    assert store.load_state("legacy") is None

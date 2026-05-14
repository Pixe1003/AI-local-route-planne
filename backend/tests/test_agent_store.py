from app.agent.state import AgentGoal, AgentState
from app.agent.store import list_sessions, load_state, save_state
from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import PlanContext
from app.schemas.pool import TimeWindow


def _state(session_id: str, user_id: str) -> AgentState:
    context = PlanContext(
        city="hefei",
        date="2026-05-08",
        time_window=TimeWindow(start="12:00", end="18:00"),
        party="friends",
        budget_per_person=180,
    )
    return AgentState(
        goal=AgentGoal(
            raw_query="安静咖啡",
            session_id=session_id,
            user_id=user_id,
            locale_city="hefei",
        ),
        profile=UserNeedProfile.from_plan_context(context, raw_query="安静咖啡"),
        context=context,
    )


def test_agent_store_persists_loads_and_lists_sessions(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.agent.store.DB_PATH", tmp_path / "agent_sessions.sqlite", raising=False)
    first = _state("session_1", "user_1")
    second = _state("session_2", "user_1")
    second.phase = "DONE"

    save_state(first)
    save_state(second)

    loaded = load_state("session_2")
    assert loaded is not None
    assert loaded.goal.session_id == "session_2"
    assert loaded.phase == "DONE"
    assert [state.goal.session_id for state in list_sessions("user_1", limit=10)] == [
        "session_2",
        "session_1",
    ]

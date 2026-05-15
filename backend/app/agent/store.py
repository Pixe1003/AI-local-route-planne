from app.agent.state import AgentState


_STATES: dict[str, AgentState] = {}


def save_state(state: AgentState) -> None:
    _STATES[state.goal.session_id] = state


def load_state(session_id: str) -> AgentState | None:
    return _STATES.get(session_id)


def list_sessions(user_id: str, limit: int = 20) -> list[AgentState]:
    sessions = [state for state in _STATES.values() if state.goal.user_id == user_id]
    return sessions[-limit:]


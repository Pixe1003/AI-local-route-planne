from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.agent.session_summarizer import summarize_session
from app.agent.state import AgentState
from app.agent.store import _conn
from app.repositories.session_vector_repo import SessionVectorRepo


def main() -> None:
    repo = SessionVectorRepo()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT state_json FROM agent_sessions ORDER BY created_at ASC"
        ).fetchall()

    print(f"Rebuilding session index from {len(rows)} sessions...")
    for row in rows:
        state = AgentState.model_validate_json(row[0])
        if state.memory.story_plan is None:
            continue
        repo.add_session(state, summarize_session(state))
    print("Done.")


if __name__ == "__main__":
    main()

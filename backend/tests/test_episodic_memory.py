from app.agent.state import AgentGoal, AgentState
from app.agent.story_models import StoryPlan, StoryStop
from app.agent.store import save_state
from app.api.routes_agent import AgentRunRequest, build_initial_state
from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import PlanContext
from app.schemas.pool import TimeWindow


def _completed_state(
    *,
    user_id: str = "memory_user",
    session_id: str = "session_1",
    query: str = "想吃合肥本地菜",
) -> AgentState:
    context = PlanContext(
        city="hefei",
        date="2026-05-08",
        time_window=TimeWindow(start="12:00", end="20:00"),
        party="friends",
        budget_per_person=180,
    )
    state = AgentState(
        goal=AgentGoal(
            raw_query=query,
            session_id=session_id,
            user_id=user_id,
            locale_city="hefei",
        ),
        profile=UserNeedProfile.from_plan_context(context, raw_query=query),
        context=context,
        phase="DONE",
    )
    state.memory.story_plan = StoryPlan(
        theme="Local Taste Route",
        narrative="A route through local restaurants.",
        stops=[
            StoryStop(
                poi_id="hf_poi_061581",
                role="opener",
                why="hotpot opener",
                ugc_quote_ref="ugc:1",
                ugc_quote="hotpot evidence",
            ),
            StoryStop(
                poi_id="hf_poi_035366",
                role="main",
                why="bbq main",
                ugc_quote_ref="ugc:2",
                ugc_quote="bbq evidence",
            ),
            StoryStop(
                poi_id="hf_poi_020889",
                role="closer",
                why="late snack closer",
                ugc_quote_ref="ugc:3",
                ugc_quote="snack evidence",
            ),
        ],
    )
    return state


def test_session_summary_captures_theme_stops_and_category_distribution() -> None:
    from app.agent.session_summarizer import summarize_session

    summary = summarize_session(_completed_state())

    assert summary.session_id == "session_1"
    assert summary.raw_query == "想吃合肥本地菜"
    assert summary.theme == "Local Taste Route"
    assert summary.stop_poi_ids == ["hf_poi_061581", "hf_poi_035366", "hf_poi_020889"]
    assert len(summary.stop_poi_names) == 3
    assert summary.category_distribution["restaurant"] >= 1


def test_build_initial_state_loads_recent_episodic_summaries(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.agent.store.DB_PATH", tmp_path / "agent_sessions.sqlite", raising=False)
    monkeypatch.setattr("app.agent.store._persist_session_vector", lambda state: None, raising=False)
    monkeypatch.setattr(
        "app.api.routes_agent._load_similar_sessions",
        lambda request, session_id: [],
        raising=False,
    )

    save_state(_completed_state(session_id="session_1"))
    save_state(_completed_state(session_id="session_2", query="想吃火锅"))

    state = build_initial_state(
        AgentRunRequest(
            user_id="memory_user",
            free_text="再来一次本地菜",
            city="hefei",
            date="2026-05-08",
            time_window=TimeWindow(start="13:00", end="19:00"),
            budget_per_person=160,
        )
    )

    assert [item.session_id for item in state.memory.episodic_summary] == [
        "session_2",
        "session_1",
    ]
    assert all(item.theme for item in state.memory.episodic_summary)


def test_build_initial_state_can_defer_similar_session_recall_to_tool(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.agent.store.DB_PATH", tmp_path / "agent_sessions.sqlite", raising=False)
    monkeypatch.setattr("app.agent.store._persist_session_vector", lambda state: None, raising=False)
    monkeypatch.setenv("PREFER_TOOL_RECALL_IN_TRACE", "true")

    from app.config import get_settings

    get_settings.cache_clear()
    save_state(_completed_state(session_id="session_1"))

    def fail_if_preloaded(request, session_id):
        raise AssertionError("similar sessions should be recalled by the tool")

    monkeypatch.setattr(
        "app.api.routes_agent._load_similar_sessions",
        fail_if_preloaded,
        raising=False,
    )

    state = build_initial_state(
        AgentRunRequest(
            user_id="memory_user",
            free_text="another local route",
            city="hefei",
            date="2026-05-08",
            time_window=TimeWindow(start="13:00", end="19:00"),
            budget_per_person=160,
        )
    )

    assert state.memory.episodic_summary
    assert state.memory.similar_sessions == []
    assert state.memory.similar_sessions_searched is False


def test_story_prompt_includes_recent_and_similar_session_memory() -> None:
    from app.agent.session_summarizer import summarize_session
    from app.agent.specialists.story_agent import CandidateEvidence, StoryAgent
    from app.schemas.user_memory import SimilarSessionHit

    state = _completed_state(query="想吃火锅")
    state.memory.episodic_summary = [summarize_session(_completed_state(session_id="old_1"))]
    state.memory.similar_sessions = [
        SimilarSessionHit(
            session_id="similar_1",
            raw_query="安静火锅路线",
            theme="Quiet Hotpot Route",
            similarity=0.91,
            stop_poi_names=["金巷子老火锅"],
            days_ago=2,
        )
    ]

    prompt = StoryAgent()._build_prompt(
        [
            CandidateEvidence(
                poi_id="hf_poi_061581",
                poi_name="金巷子老火锅",
                category="restaurant",
                score=0.9,
                price_per_person=None,
                quote_ref="ugc:1",
                quote="hotpot evidence",
            )
        ],
        state,
    )

    assert "recent route history" in prompt
    assert "Semantically similar past sessions" in prompt
    assert "Quiet Hotpot Route" in prompt

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.agent.state import AgentGoal, AgentState
from app.agent.story_models import StoryPlan, StoryStop
from app.agent.store import save_state
from app.main import app
from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import PlanContext
from app.schemas.pool import TimeWindow


client = TestClient(app)


def _state(
    *,
    session_id: str,
    user_id: str = "facts_user",
    query: str = "想吃火锅",
    budget: int = 180,
    rejected_poi_id: str | None = None,
) -> AgentState:
    context = PlanContext(
        city="hefei",
        date="2026-05-09",
        time_window=TimeWindow(start="18:00", end="22:00"),
        party="friends",
        budget_per_person=budget,
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
        narrative="A route through local food.",
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
    if rejected_poi_id:
        state.memory.feedback_applied = True
        state.memory.feedback_intent = {
            "event_type": "REPLACE_POI",
            "_original_poi_at_target": rejected_poi_id,
        }
    return state


def test_user_facts_are_derived_from_saved_sessions(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.agent.store.DB_PATH", tmp_path / "agent_sessions.sqlite", raising=False)
    monkeypatch.setattr("app.agent.store._persist_session_vector", lambda state: None, raising=False)

    save_state(_state(session_id="s1", budget=120, rejected_poi_id="hf_poi_061581"))
    save_state(_state(session_id="s2", budget=220, query="还想吃本地菜"))

    from app.agent.user_memory import get_user_facts

    facts = get_user_facts("facts_user", force_refresh=True)

    assert facts.user_id == "facts_user"
    assert facts.session_count == 2
    assert facts.typical_budget_range == (120, 220)
    assert facts.typical_party_type == "friends"
    assert "restaurant" in facts.favorite_categories
    assert "hf_poi_061581" in facts.rejected_poi_ids
    assert "likes=restaurant" in facts.to_prompt_block()


def test_save_state_invalidates_user_facts_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.agent.store.DB_PATH", tmp_path / "agent_sessions.sqlite", raising=False)
    monkeypatch.setattr("app.agent.store._persist_session_vector", lambda state: None, raising=False)

    from app.agent.user_memory import get_user_facts

    save_state(_state(session_id="s1", budget=100))
    assert get_user_facts("facts_user", force_refresh=True).session_count == 1

    save_state(_state(session_id="s2", budget=200))

    assert get_user_facts("facts_user").session_count == 2


def test_fact_alignment_penalizes_rejected_pois() -> None:
    from app.repositories.poi_repo import get_poi_repository
    from app.schemas.user_memory import UserFacts
    from app.services.poi_scoring_service import PoiScoringService

    poi = get_poi_repository().get("hf_poi_061581")
    facts = UserFacts(
        user_id="facts_user",
        favorite_categories=["restaurant"],
        rejected_poi_ids=["hf_poi_061581"],
        session_count=3,
        updated_at=datetime.now(timezone.utc),
    )

    score = PoiScoringService().score_poi(poi, user_facts=facts)

    assert score.fact_alignment <= -8.0
    assert score.total < 80


def test_user_facts_api_returns_derived_facts(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.agent.store.DB_PATH", tmp_path / "agent_sessions.sqlite", raising=False)
    monkeypatch.setattr("app.agent.store._persist_session_vector", lambda state: None, raising=False)

    save_state(_state(session_id="s1", rejected_poi_id="hf_poi_061581"))

    response = client.get("/api/agent/user/facts_user/facts?force_refresh=true")

    assert response.status_code == 200
    assert response.json()["session_count"] == 1
    assert "hf_poi_061581" in response.json()["rejected_poi_ids"]

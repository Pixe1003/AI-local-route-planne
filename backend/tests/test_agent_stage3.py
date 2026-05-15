from typing import Any

from fastapi.testclient import TestClient

from app.agent.specialists.critic import Critic
from app.agent.specialists.story_agent import StoryAgent, StoryPlan, StoryStop
from app.agent.state import AgentGoal, AgentState
from app.api import routes_route
from app.main import app
from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import (
    HardConstraints,
    PlanContext,
    SoftPreferences,
    StructuredIntent,
    ValidationIssue,
    ValidationResult,
)
from app.schemas.pool import PoolRequest, TimeWindow
from app.services.amap.schemas import AmapRouteMode, AmapRouteResult, AmapRouteStep
from app.services.pool_service import PoolService


client = TestClient(app)


def _intent(context: PlanContext) -> StructuredIntent:
    return StructuredIntent(
        hard_constraints=HardConstraints(
            start_time=context.time_window.start,
            end_time=context.time_window.end,
            budget_total=context.budget_per_person,
            must_include_meal=True,
        ),
        soft_preferences=SoftPreferences(
            pace="balanced",
            avoid_queue=True,
            photography_priority=True,
            food_diversity=True,
            custom_notes=["quiet local food and photos"],
        ),
        must_visit_pois=[],
        avoid_pois=[],
    )


def _state_with_pool() -> AgentState:
    context = PlanContext(
        city="shanghai",
        date="2026-05-08",
        time_window=TimeWindow(start="14:00", end="20:00"),
        party="friends",
        budget_per_person=180,
    )
    profile = UserNeedProfile.from_plan_context(context, raw_query="quiet local food and photos")
    pool = PoolService().generate_pool(
        PoolRequest(
            user_id="mock_user",
            city="shanghai",
            date=context.date,
            time_window=context.time_window,
            party="friends",
            budget_per_person=180,
            free_text="quiet local food and photos",
        )
    )
    state = AgentState(
        goal=AgentGoal(raw_query="quiet local food and photos", user_id="mock_user", locale_city="shanghai"),
        profile=profile,
        context=context,
    )
    state.memory.intent = _intent(context)
    state.memory.pool = pool
    return state


def _patch_route_client(monkeypatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    class FakeRouteClient:
        def get_route(self, **kwargs: Any) -> AmapRouteResult:
            calls.append(kwargs)
            return AmapRouteResult(
                mode=AmapRouteMode.DRIVING,
                distance_m=900 + len(calls),
                duration_s=480,
                steps=[
                    AmapRouteStep(
                        instruction="drive",
                        road_name="demo road",
                        distance_m=900,
                        duration_s=480,
                        polyline_coordinates=[[121.49, 31.24], [121.48, 31.23]],
                    )
                ],
                polyline_coordinates=[],
                raw_response={"status": "1"},
            )

        def close(self) -> None:
            return None

    monkeypatch.setattr(routes_route, "AmapRouteClient", FakeRouteClient, raising=False)
    return calls


def test_story_agent_fallback_builds_story_with_verifiable_evidence() -> None:
    state = _state_with_pool()

    story = StoryAgent().compose(state)
    candidate_ids = {poi.id for category in state.memory.pool.categories for poi in category.pois}

    assert story.theme
    assert story.narrative
    assert 3 <= len(story.stops) <= 5
    assert {stop.poi_id for stop in story.stops} <= candidate_ids
    assert all(stop.why and stop.ugc_quote_ref and stop.ugc_quote for stop in story.stops)
    assert StoryAgent().post_check(story, state) == []


def test_story_agent_post_check_rejects_hallucinated_poi_and_quote() -> None:
    state = _state_with_pool()
    bad = StoryPlan(
        theme="bad",
        narrative="bad",
        stops=[
            StoryStop(
                poi_id="made_up_poi",
                role="opener",
                why="invented quote",
                ugc_quote_ref="made_up_quote",
                ugc_quote="invented quote",
                suggested_dwell_min=30,
            )
        ],
        dropped=[],
    )

    issues = StoryAgent().post_check(bad, state)

    assert "hallucinated_poi" in issues
    assert "hallucinated_ugc" in issues


def test_critic_scores_story_and_blocks_invalid_validation() -> None:
    state = _state_with_pool()
    state.memory.story_plan = StoryAgent().compose(state)
    state.memory.validation = ValidationResult(is_valid=True)

    critique = Critic().review(state)

    assert critique.should_stop is True
    assert critique.evidence_strength >= 7

    state.memory.validation = ValidationResult(
        is_valid=False,
        issues=[ValidationIssue(code="time_budget_exceeded", message="too long")],
    )

    blocked = Critic().review(state)

    assert blocked.should_stop is False
    assert "time_budget_exceeded" in blocked.issues


def test_agent_full_pipeline_returns_story_validation_and_critique(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    route_calls = _patch_route_client(monkeypatch)

    response = client.post(
        "/api/agent/run",
        json={
            "user_id": "mock_user",
            "free_text": "quiet local food and photos",
            "city": "shanghai",
            "date": "2026-05-08",
            "time_window": {"start": "14:00", "end": "20:00"},
            "budget_per_person": 180,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["phase"] == "DONE"
    assert data["story_plan"]["theme"]
    assert data["story_plan"]["narrative"]
    assert data["story_plan"]["stops"]
    assert data["validation"]["is_valid"] is True
    assert data["critique"]["should_stop"] is True
    assert [step["tool_name"] for step in data["steps"]] == [
        "parse_intent",
        "search_ugc_evidence",
        "recommend_pool",
        "compose_story",
        "get_amap_chain",
        "validate_route",
        "critique",
    ]
    assert len(route_calls) == len(data["ordered_poi_ids"]) - 1

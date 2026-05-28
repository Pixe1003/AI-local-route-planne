from datetime import datetime
from types import SimpleNamespace

from app.agent.conductor import Conductor
from app.agent.state import AgentGoal, AgentState
from app.agent.tools import get_tool_registry
from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import HardConstraints, PlanContext, SoftPreferences, StructuredIntent
from app.schemas.pool import PoiInPool, PoolCategory, PoolMeta, PoolResponse, TimeWindow


def _pool() -> PoolResponse:
    return PoolResponse(
        pool_id="pool_solver",
        default_selected_ids=["closed", "restaurant", "museum", "cafe"],
        categories=[
            PoolCategory(
                name="all",
                description="all",
                pois=[
                    PoiInPool(
                        id="closed",
                        name="Closed Scenic",
                        category="scenic",
                        latitude=31.80,
                        longitude=117.20,
                        rating=4.9,
                        price_per_person=20,
                        cover_image=None,
                        distance_meters=None,
                        why_recommend="closed but high score",
                        highlight_quote="closed",
                        keywords=[],
                        estimated_queue_min=5,
                        suitable_score=0.99,
                    ),
                    PoiInPool(
                        id="restaurant",
                        name="Local Food",
                        category="restaurant",
                        latitude=31.81,
                        longitude=117.21,
                        rating=4.6,
                        price_per_person=30,
                        cover_image=None,
                        distance_meters=None,
                        why_recommend="food",
                        highlight_quote="food",
                        keywords=[],
                        estimated_queue_min=10,
                        suitable_score=0.9,
                    ),
                    PoiInPool(
                        id="museum",
                        name="Museum",
                        category="culture",
                        latitude=31.82,
                        longitude=117.22,
                        rating=4.5,
                        price_per_person=20,
                        cover_image=None,
                        distance_meters=None,
                        why_recommend="culture",
                        highlight_quote="culture",
                        keywords=[],
                        estimated_queue_min=10,
                        suitable_score=0.8,
                    ),
                    PoiInPool(
                        id="cafe",
                        name="Cafe",
                        category="cafe",
                        latitude=31.83,
                        longitude=117.23,
                        rating=4.4,
                        price_per_person=10,
                        cover_image=None,
                        distance_meters=None,
                        why_recommend="cafe",
                        highlight_quote="cafe",
                        keywords=[],
                        estimated_queue_min=5,
                        suitable_score=0.7,
                    ),
                ],
            )
        ],
        meta=PoolMeta(total_count=4, generated_at=datetime(2026, 5, 26), user_persona_summary="solver"),
    )


def _state() -> AgentState:
    context = PlanContext(
        city="hefei",
        date="2026-05-26",
        time_window=TimeWindow(start="09:00", end="11:00"),
        party="friends",
        budget_per_person=60,
    )
    state = AgentState(
        goal=AgentGoal(raw_query="local food and museum", session_id="solver_session", user_id="solver_user"),
        profile=UserNeedProfile.from_plan_context(context, raw_query="local food and museum"),
        context=context,
    )
    state.memory.intent = StructuredIntent(
        hard_constraints=HardConstraints(
            start_time="09:00",
            end_time="11:00",
            budget_total=60,
            must_include_meal=True,
            must_include_experience=True,
        ),
        soft_preferences=SoftPreferences(),
        must_visit_pois=["museum"],
        avoid_pois=[],
    )
    state.memory.pool = _pool()
    state.memory.ugc_searched = True
    return state


def test_rule_decision_solves_constrained_route_before_story_composition() -> None:
    state = _state()

    decision = Conductor(get_tool_registry(), llm=object())._rule_based_decision(state)

    assert decision.tool == "solve_constrained_route"
    assert set(decision.args) <= {"max_stops", "solver_mode", "time_limit_seconds"}


def test_solve_constrained_route_tool_rewrites_pool_selection_and_records_optimization(monkeypatch) -> None:
    repo = {
        "closed": SimpleNamespace(
            id="closed",
            category="scenic",
            visit_duration=20,
            price_per_person=20,
            open_hours={"tuesday": [{"open": "12:00", "close": "18:00"}]},
        ),
        "restaurant": SimpleNamespace(
            id="restaurant",
            category="restaurant",
            visit_duration=20,
            price_per_person=30,
            open_hours={"tuesday": [{"open": "09:00", "close": "18:00"}]},
        ),
        "museum": SimpleNamespace(
            id="museum",
            category="culture",
            visit_duration=20,
            price_per_person=20,
            open_hours={"tuesday": [{"open": "09:00", "close": "18:00"}]},
        ),
        "cafe": SimpleNamespace(
            id="cafe",
            category="cafe",
            visit_duration=20,
            price_per_person=10,
            open_hours={"tuesday": [{"open": "09:00", "close": "18:00"}]},
        ),
    }

    class FakeRepo:
        def get_many(self, poi_ids):
            return [repo[poi_id] for poi_id in poi_ids if poi_id in repo]

    monkeypatch.setattr("app.agent.tools.get_poi_repository", lambda: FakeRepo())
    state = _state()

    result = get_tool_registry().execute(
        "solve_constrained_route",
        state,
        {"max_stops": 3, "solver_mode": "optw", "time_limit_seconds": 2},
    )

    pool = result.memory_patch["pool"]
    assert pool.default_selected_ids == ["restaurant", "museum", "cafe"]
    assert result.memory_patch["route_optimization"]["constraint_violations"] == []
    assert result.next_phase == "COMPOSING"

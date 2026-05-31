from datetime import datetime
from types import SimpleNamespace

from app.agent.conductor import Conductor
from app.agent.state import AgentGoal, AgentState
from app.agent.story_models import StoryPlan, StoryStop
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


def test_solve_constrained_route_caps_pareto_profile_time_limit(monkeypatch) -> None:
    from app.solver.optw import OptwResult

    repo = {
        "closed": SimpleNamespace(
            id="closed",
            category="scenic",
            visit_duration=20,
            price_per_person=20,
            open_hours={"tuesday": [{"open": "09:00", "close": "18:00"}]},
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

    recorded: dict[str, float] = {}

    def fake_solve_optw(*args, **kwargs):
        return OptwResult(
            ordered_ids=["restaurant", "museum", "cafe"],
            solver="fake",
            objective_value=1.0,
            selected_utility=1.0,
            total_duration_min=80,
            total_cost=60,
        )

    def fake_build_pareto_variants(*args, **kwargs):
        recorded["time_limit_seconds"] = kwargs["solve_kwargs"]["time_limit_seconds"]
        return []

    monkeypatch.setattr("app.agent.tools.get_poi_repository", lambda: FakeRepo())
    monkeypatch.setattr("app.agent.tools.solve_optw", fake_solve_optw)
    monkeypatch.setattr("app.agent.tools.build_pareto_variants", fake_build_pareto_variants)

    result = get_tool_registry().execute(
        "solve_constrained_route",
        _state(),
        {"max_stops": 3, "solver_mode": "optw", "time_limit_seconds": 3},
    )

    assert result.memory_patch["pool"].default_selected_ids == ["restaurant", "museum", "cafe"]
    assert recorded["time_limit_seconds"] <= 0.5


def test_validate_route_waits_until_poi_opens(monkeypatch) -> None:
    repo = {
        "restaurant": SimpleNamespace(
            id="restaurant",
            name="Local Food",
            category="restaurant",
            visit_duration=20,
            price_per_person=20,
            queue_estimate={"weekend_peak": 10},
            open_hours={"tuesday": [{"open": "10:00", "close": "18:00"}]},
        ),
        "museum": SimpleNamespace(
            id="museum",
            name="Museum",
            category="culture",
            visit_duration=20,
            price_per_person=10,
            queue_estimate={"weekend_peak": 10},
            open_hours={"tuesday": [{"open": "09:00", "close": "18:00"}]},
        ),
        "cafe": SimpleNamespace(
            id="cafe",
            name="Cafe",
            category="cafe",
            visit_duration=20,
            price_per_person=10,
            queue_estimate={"weekend_peak": 10},
            open_hours={"tuesday": [{"open": "09:00", "close": "18:00"}]},
        ),
    }

    class FakeRepo:
        def get_many(self, poi_ids):
            return [repo[poi_id] for poi_id in poi_ids if poi_id in repo]

        def list_by_city(self, city):
            return list(repo.values())

    fake_repo = FakeRepo()
    monkeypatch.setattr("app.agent.tools.get_poi_repository", lambda: fake_repo)
    monkeypatch.setattr("app.services.route_validator.get_poi_repository", lambda: fake_repo)
    state = _state()
    state.context.time_window.start = "09:30"
    state.context.time_window.end = "12:00"
    state.memory.intent.hard_constraints.start_time = "09:30"
    state.memory.intent.hard_constraints.end_time = "12:00"
    state.memory.intent.hard_constraints.budget_total = 50
    state.memory.story_plan = StoryPlan(
        theme="Opening Window",
        narrative="A compact route.",
        stops=[
            StoryStop(
                poi_id="restaurant",
                role="opener",
                why="restaurant stop",
                ugc_quote_ref="pool:restaurant",
                ugc_quote="restaurant",
                suggested_dwell_min=20,
            ),
            StoryStop(
                poi_id="museum",
                role="midway",
                why="culture stop",
                ugc_quote_ref="pool:museum",
                ugc_quote="museum",
                suggested_dwell_min=20,
            ),
            StoryStop(
                poi_id="cafe",
                role="closer",
                why="cafe stop",
                ugc_quote_ref="pool:cafe",
                ugc_quote="cafe",
                suggested_dwell_min=20,
            ),
        ],
    )

    result = get_tool_registry().execute("validate_route", state, {})

    assert result.payload.is_valid is True
    assert [issue.code for issue in result.payload.issues] == []

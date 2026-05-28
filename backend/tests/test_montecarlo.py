from app.agent.conductor import Conductor
from app.agent.story_models import StoryPlan, StoryStop
from app.agent.state import AgentGoal, AgentState
from app.agent.tools import get_tool_registry
from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import HardConstraints, PlanContext, RouteMetrics, RouteSkeleton, RouteStop, SoftPreferences, StructuredIntent, Transport, ValidationResult
from app.schemas.pool import PoolMeta, PoolResponse, TimeWindow
from app.schemas.route import RouteChainResponse
from app.services.amap.schemas import AmapRouteMode
from app.sim.montecarlo import simulate


def _skeleton(duration: int) -> RouteSkeleton:
    return RouteSkeleton(
        style="story",
        stops=[
            RouteStop(poi_id="a", arrival_time="09:00", departure_time="09:30", duration_min=duration, transport_to_next=Transport(mode="driving", duration_min=10, distance_meters=1000)),
            RouteStop(poi_id="b", arrival_time="09:40", departure_time="10:10", duration_min=duration),
        ],
        dropped_poi_ids=[],
        drop_reasons={},
        metrics=RouteMetrics(total_duration_min=duration * 2 + 10, total_cost=0, poi_count=2, walking_distance_meters=0, queue_total_min=20),
    )


def test_montecarlo_is_reproducible_and_distinguishes_risk() -> None:
    stable = simulate(_skeleton(20), {"a": 5, "b": 5}, end_min=660, n=200, seed=7)
    stable_again = simulate(_skeleton(20), {"a": 5, "b": 5}, end_min=660, n=200, seed=7)
    risky = simulate(_skeleton(45), {"a": 25, "b": 25}, end_min=660, n=200, seed=7)

    assert stable == stable_again
    assert stable.on_time_prob > risky.on_time_prob
    assert stable.expected_overflow_min < risky.expected_overflow_min


def test_conductor_assesses_robustness_after_validation() -> None:
    context = PlanContext(
        city="hefei",
        date="2026-05-26",
        time_window=TimeWindow(start="09:00", end="12:00"),
        party="friends",
        budget_per_person=100,
    )
    state = AgentState(
        goal=AgentGoal(raw_query="route", session_id="robust", user_id="u"),
        profile=UserNeedProfile.from_plan_context(context, raw_query="route"),
        context=context,
    )
    state.memory.intent = StructuredIntent(
        hard_constraints=HardConstraints(start_time="09:00", end_time="12:00"),
        soft_preferences=SoftPreferences(),
        must_visit_pois=[],
        avoid_pois=[],
    )
    state.memory.ugc_searched = True
    state.memory.pool = PoolResponse(
        pool_id="p",
        categories=[],
        default_selected_ids=[],
        meta=PoolMeta(total_count=0, generated_at="2026-05-26T00:00:00Z", user_persona_summary="test"),
    )
    state.memory.route_optimization = {"solver": "test"}
    state.memory.story_plan = StoryPlan(
        theme="t",
        narrative="n",
        stops=[
            StoryStop(poi_id="a", role="main", why="a", ugc_quote_ref="pool:a", ugc_quote="a"),
            StoryStop(poi_id="b", role="rest", why="b", ugc_quote_ref="pool:b", ugc_quote="b"),
        ],
    )
    state.memory.route_chain = RouteChainResponse(
        mode=AmapRouteMode.DRIVING,
        ordered_pois=[],
        total_distance_m=0,
        total_duration_s=0,
        segments=[],
        geojson={"type": "FeatureCollection", "features": []},
    )
    state.memory.validation = ValidationResult(is_valid=True)
    state.memory.critique = None

    decision = Conductor(get_tool_registry(), llm=object())._rule_based_decision(state)

    assert decision.tool == "assess_robustness"

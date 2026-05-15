from types import SimpleNamespace
import time

from app.agent import conductor
from app.agent.conductor import Conductor
from app.agent.state import AgentGoal, AgentState
from app.agent.story_models import StoryPlan, StoryStop
from app.agent.tools import _critique, get_tool_registry
from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import PlanContext, ScoreBreakdown, ValidationIssue, ValidationResult
from app.schemas.pool import PoolRequest, TimeWindow
from app.schemas.route import RouteChainRequest, RoutePoi
from app.services.amap.schemas import AmapRouteMode, AmapRouteResult, AmapRouteStep
from app.services.pool_service import PoolService


def _context() -> PlanContext:
    return PlanContext(
        city="hefei",
        date="2026-05-08",
        time_window=TimeWindow(start="14:00", end="20:00"),
        party="friends",
        budget_per_person=180,
    )


def _state() -> AgentState:
    context = _context()
    return AgentState(
        goal=AgentGoal(raw_query="local food", user_id="perf_user"),
        profile=UserNeedProfile.from_plan_context(context, raw_query="local food"),
        context=context,
        phase="DONE",
    )


def test_pool_generation_shortlists_before_expensive_scoring(monkeypatch) -> None:
    service = PoolService()
    expensive_calls = 0

    def fake_score_poi(*args, **kwargs) -> ScoreBreakdown:
        nonlocal expensive_calls
        expensive_calls += 1
        return ScoreBreakdown(user_interest=10, poi_quality=10, total=50)

    monkeypatch.setattr(service.poi_scorer, "score_poi", fake_score_poi)
    monkeypatch.setattr(service, "_highlight_quote", lambda poi, free_text, ugc_hits=None: poi.name)

    response = service.generate_pool(
        PoolRequest(
            user_id="perf_user",
            city="hefei",
            date="2026-05-08",
            time_window=TimeWindow(start="14:00", end="20:00"),
            party="friends",
            budget_per_person=180,
            free_text="今天下午想少排队、吃本地菜、顺路拍照",
        )
    )

    assert response.meta.total_count == 24
    assert expensive_calls <= 32


def test_save_state_does_not_block_on_session_vector_indexing(tmp_path, monkeypatch) -> None:
    from app.agent import store

    monkeypatch.setattr(store, "DB_PATH", tmp_path / "agent_sessions.sqlite", raising=False)

    def slow_vector_persist(state):
        time.sleep(0.6)

    monkeypatch.setattr(store, "_persist_session_vector", slow_vector_persist)

    start = time.perf_counter()
    store.save_state(_state())
    elapsed = time.perf_counter() - start

    assert elapsed < 0.2


def test_fast_decision_mode_skips_llm_tool_selection(monkeypatch) -> None:
    monkeypatch.setattr(
        conductor,
        "get_settings",
        lambda: SimpleNamespace(agent_tool_calling_enabled=True, agent_fast_decision_enabled=True),
    )

    class FailingLlm:
        def complete_tool_call(self, *args, **kwargs):
            raise AssertionError("fast decision mode should use deterministic fallback decisions")

    state = _state()
    state.phase = "CREATED"
    state.memory.intent = None

    decision = Conductor(get_tool_registry(), FailingLlm())._decide(state)

    assert decision.tool == "parse_intent"
    assert decision.args == {"free_text": "local food"}


def test_time_budget_exceeded_compacts_story_instead_of_retrying_story() -> None:
    context = _context()
    state = AgentState(
        goal=AgentGoal(raw_query="local food", user_id="perf_user"),
        profile=UserNeedProfile.from_plan_context(context, raw_query="local food"),
        context=context,
    )
    state.memory.story_plan = StoryPlan(
        theme="Local Taste Route",
        narrative="too long",
        stops=[
            StoryStop(
                poi_id=f"poi_{index}",
                role=["opener", "midway", "main", "rest", "closer"][index],
                why="why",
                ugc_quote_ref="pool:test",
                ugc_quote="quote",
            )
            for index in range(5)
        ],
    )
    state.memory.validation = ValidationResult(
        is_valid=False,
        issues=[ValidationIssue(code="time_budget_exceeded", message="too long")],
    )

    result = _critique(state, {})

    assert result.next_phase == "COMPOSING"
    assert len(result.memory_patch["story_plan"].stops) == 3
    assert result.memory_patch["route_chain"] is None
    assert result.memory_patch["validation"] is None
    assert result.memory_patch["story_retry_count"] == 1
    assert "story_plan" in result.memory_patch


def test_compact_route_ids_drops_far_stops_before_amap_call() -> None:
    from app.agent.tools import _compact_route_ids

    class FakeRepo:
        def __init__(self) -> None:
            self._pois = {
                "a": SimpleNamespace(id="a", latitude=31.8200, longitude=117.2200, category="restaurant"),
                "b": SimpleNamespace(id="b", latitude=31.8210, longitude=117.2210, category="culture"),
                "c": SimpleNamespace(id="c", latitude=31.8220, longitude=117.2220, category="cafe"),
                "d": SimpleNamespace(id="d", latitude=31.8230, longitude=117.2230, category="scenic"),
                "far": SimpleNamespace(id="far", latitude=32.5000, longitude=118.5000, category="nightlife"),
            }

        def get_many(self, poi_ids):
            return [self._pois[poi_id] for poi_id in poi_ids if poi_id in self._pois]

    compacted = _compact_route_ids(
        ["a", "far", "b", "c", "d"],
        FakeRepo(),
        max_stops=4,
        max_segment_m=8_000,
        max_total_m=15_000,
    )

    assert compacted == ["a", "b", "c", "d"]


def test_route_chain_reuses_cached_segment_for_identical_pairs() -> None:
    from app.api import routes_route

    if hasattr(routes_route, "_SEGMENT_ROUTE_CACHE"):
        routes_route._SEGMENT_ROUTE_CACHE.clear()

    class FakeClient:
        def __init__(self) -> None:
            self.calls = 0

        def get_route(self, **kwargs):
            self.calls += 1
            return AmapRouteResult(
                mode=AmapRouteMode.DRIVING,
                distance_m=1200,
                duration_s=600,
                steps=[
                    AmapRouteStep(
                        instruction="drive",
                        road_name="demo",
                        distance_m=1200,
                        duration_s=600,
                        polyline_coordinates=[[117.22, 31.82], [117.23, 31.83]],
                    )
                ],
                polyline_coordinates=[],
                raw_response={"status": "1"},
            )

    payload = RouteChainRequest(mode=AmapRouteMode.DRIVING)
    route_pois = [
        RoutePoi(id="a", name="A", longitude=117.22, latitude=31.82, category="restaurant"),
        RoutePoi(id="b", name="B", longitude=117.23, latitude=31.83, category="culture"),
    ]
    client = FakeClient()

    routes_route.build_route_chain(payload=payload, route_pois=route_pois, client=client)
    routes_route.build_route_chain(payload=payload, route_pois=route_pois, client=client)

    assert client.calls == 1

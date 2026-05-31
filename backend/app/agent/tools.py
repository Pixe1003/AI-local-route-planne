from collections.abc import Callable
from dataclasses import dataclass
from datetime import date as date_type
from typing import Any

from pydantic import BaseModel, Field

from app.agent import tool_schemas
from app.agent.state import AgentPhase, AgentState
from app.agent.specialists.critic import Critic
from app.agent.specialists.repair_agent import RepairAgent
from app.agent.specialists.story_agent import StoryAgent
from app.agent.story_models import RobustnessSummary, RouteOptimizationSummary, StoryStop
from app.api import routes_route
from app.repositories.ugc_vector_repo import get_ugc_vector_repo
from app.repositories.poi_repo import get_poi_repository
from app.schemas.plan import (
    HardConstraints,
    RouteMetrics,
    RouteSkeleton,
    RouteStop,
    SoftPreferences,
    StructuredIntent,
    Transport,
)
from app.schemas.pool import PoolRequest
from app.schemas.route import RouteChainRequest
from app.services.amap.schemas import AmapRouteMode
from app.services.category_policy import EXPERIENCE_CATEGORIES
from app.services.pool_service import PoolService
from app.services.route_validator import RouteValidator
from app.solver.distance import haversine_meters
from app.solver.optw import OptwNode, solve_optw
from app.solver.pareto import build_pareto_variants
from app.sim.montecarlo import simulate
from app.utils.time_utils import add_minutes, minutes_between


PARETO_PROFILE_TIME_LIMIT_SECONDS = 0.5


class ToolResult(BaseModel):
    observation_summary: str
    payload: Any | None = None
    memory_patch: dict[str, Any] = Field(default_factory=dict)
    next_phase: AgentPhase | None = None
    observation_payload_ref: str | None = None


@dataclass(frozen=True)
class Tool:
    name: str
    schema: dict[str, Any]
    handler: Callable[[AgentState, dict[str, Any]], ToolResult]
    timeout_s: float = 10.0


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def schemas_for_llm(self) -> list[dict[str, Any]]:
        return [tool.schema for tool in self._tools.values()]

    def execute(self, name: str, state: AgentState, args: dict[str, Any]) -> ToolResult:
        tool = self._tools[name]
        return tool.handler(state, args)


def get_tool_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            Tool("parse_intent", tool_schemas.PARSE_INTENT, _parse_intent),
            Tool("search_ugc_evidence", tool_schemas.SEARCH_UGC_EVIDENCE, _search_ugc_evidence),
            Tool("recall_similar_sessions", tool_schemas.RECALL_SIMILAR_SESSIONS, _recall_similar_sessions),
            Tool("recommend_pool", tool_schemas.RECOMMEND_POOL, _recommend_pool),
            Tool("solve_constrained_route", tool_schemas.SOLVE_CONSTRAINED_ROUTE, _solve_constrained_route),
            Tool("compose_story", tool_schemas.COMPOSE_STORY, _compose_story),
            Tool("get_amap_chain", tool_schemas.GET_AMAP_CHAIN, _get_amap_chain),
            Tool("parse_feedback", tool_schemas.PARSE_FEEDBACK, _parse_feedback),
            Tool("replan_by_event", tool_schemas.REPLAN_BY_EVENT, _replan_by_event),
            Tool("validate_route", tool_schemas.VALIDATE_ROUTE, _validate_route),
            Tool("assess_robustness", tool_schemas.ASSESS_ROBUSTNESS, _assess_robustness),
            Tool("critique", tool_schemas.CRITIQUE, _critique),
        ]
    )


def _parse_intent(state: AgentState, args: dict[str, Any]) -> ToolResult:
    free_text = str(args.get("free_text") or state.goal.raw_query)
    selected_poi_ids = list(args.get("selected_poi_ids") or [])
    intent = _rule_parse_intent(state, free_text, selected_poi_ids)
    return ToolResult(
        observation_summary="Parsed route intent from user request.",
        payload=intent,
        memory_patch={"intent": intent},
        next_phase="RETRIEVING",
    )


def _rule_parse_intent(
    state: AgentState,
    free_text: str,
    selected_poi_ids: list[str],
) -> StructuredIntent:
    budget_total = state.context.budget_per_person
    if budget_total is None and state.memory.user_facts and state.memory.user_facts.typical_budget_range:
        _, budget_total = state.memory.user_facts.typical_budget_range
    if budget_total is not None and state.context.party == "couple":
        budget_total *= 2
    avoid_queue = any(keyword in free_text for keyword in ["少排队", "不排队", "排队少", "别排队"])
    photography = any(keyword in free_text for keyword in ["拍照", "打卡", "出片"])
    food = any(keyword in free_text for keyword in ["吃", "餐", "美食", "本地菜", "火锅"])
    pace = "efficient" if any(keyword in free_text for keyword in ["高效", "多逛", "多走"]) else "balanced"
    if any(keyword in free_text for keyword in ["轻松", "慢", "松弛"]):
        pace = "relaxed"
    avoid_pois = []
    if state.memory.user_facts:
        avoid_pois.extend(state.memory.user_facts.rejected_poi_ids)
    avoid_pois.extend(state.profile.must_avoid)
    return StructuredIntent(
        hard_constraints=HardConstraints(
            start_time=state.context.time_window.start,
            end_time=state.context.time_window.end,
            budget_total=budget_total,
            transport_mode="mixed",
            must_include_meal=food,
        ),
        soft_preferences=SoftPreferences(
            pace=pace,
            avoid_queue=avoid_queue,
            weather_sensitive=any(keyword in free_text for keyword in ["下雨", "雨天", "室内"]),
            photography_priority=photography,
            food_diversity=food,
            custom_notes=[free_text] if free_text else [],
        ),
        must_visit_pois=selected_poi_ids,
        avoid_pois=list(dict.fromkeys(avoid_pois)),
    )


def _search_ugc_evidence(state: AgentState, args: dict[str, Any]) -> ToolResult:
    query = str(args.get("query") or args.get("free_text") or state.goal.raw_query)
    city = str(args.get("city") or state.context.city)
    top_k = int(args.get("top_k") or 8)
    hits = get_ugc_vector_repo().search(query, city=city, top_k=top_k)
    payload = [hit.model_dump() for hit in hits]
    return ToolResult(
        observation_summary=f"Found {len(payload)} UGC evidence snippets for route retrieval.",
        payload=payload,
        memory_patch={"ugc_hits": payload, "ugc_searched": True},
        next_phase="RETRIEVING",
    )


def _recall_similar_sessions(state: AgentState, args: dict[str, Any]) -> ToolResult:
    from app.repositories.session_vector_repo import get_session_vector_repo

    query = str(args.get("query") or state.goal.raw_query)
    top_k = int(args.get("top_k") or 3)
    hits = get_session_vector_repo().search_similar(
        state.goal.user_id,
        query,
        top_k=top_k,
        exclude_session_id=state.goal.session_id,
    )
    return ToolResult(
        observation_summary=f"Recalled {len(hits)} similar past sessions.",
        payload=[hit.model_dump() for hit in hits],
        memory_patch={"similar_sessions": hits, "similar_sessions_searched": True},
        next_phase=state.phase,
    )


def _recommend_pool(state: AgentState, args: dict[str, Any]) -> ToolResult:
    free_text = str(args.get("free_text") or state.goal.raw_query)
    city = str(args.get("city") or state.context.city)
    request = PoolRequest(
        user_id=state.goal.user_id,
        city=city,
        date=state.context.date,
        time_window=state.context.time_window,
        party=state.context.party,
        budget_per_person=state.context.budget_per_person,
        free_text=free_text,
        need_profile=state.profile,
        preference_snapshot=state.preference,
        user_facts=state.memory.user_facts,
        ugc_hits=state.memory.ugc_hits,
        origin_latitude=state.context.origin_latitude,
        origin_longitude=state.context.origin_longitude,
        radius_meters=state.context.radius_meters,
    )
    service = PoolService()
    pool = service.generate_pool(request)
    retrieval_stats = getattr(service, "last_retrieval_stats", {})
    return ToolResult(
        observation_summary=(
            f"Generated candidate pool with {pool.meta.total_count} POIs "
            f"and {len(pool.default_selected_ids)} default route ids; "
            f"retrieve_candidates={retrieval_stats.get('total_candidates', 0)} "
            f"rerank_candidates={retrieval_stats.get('rerank_candidates', 0)} "
            f"pool_selected={retrieval_stats.get('pool_selected', pool.meta.total_count)}."
        ),
        payload=pool,
        memory_patch={"pool": pool},
        next_phase="CHECKING",
    )


def _solve_constrained_route(state: AgentState, args: dict[str, Any]) -> ToolResult:
    if state.memory.pool is None or state.memory.intent is None:
        return ToolResult(
            observation_summary="Skipped constrained route solving because pool or intent is missing.",
            memory_patch={
                "route_optimization": {
                    "solver": "skipped",
                    "objective_value": 0,
                    "selected_utility": 0,
                    "constraint_violations": ["missing_pool_or_intent"],
                    "optimality_gap": None,
                    "fallback_used": True,
                }
            },
            next_phase="COMPOSING",
        )

    pool = state.memory.pool.model_copy(deep=True)
    max_stops = int(args.get("max_stops") or 5)
    solver_mode = str(args.get("solver_mode") or "optw")
    time_limit_seconds = float(args.get("time_limit_seconds") or 3)
    pool_pois = [poi for category in pool.categories for poi in category.pois]
    pool_by_id = {poi.id: poi for poi in pool_pois}
    candidate_ids = list(pool_by_id)
    repo_pois = get_poi_repository().get_many(candidate_ids)
    repo_by_id = {poi.id: poi for poi in repo_pois}
    start_min = _hhmm_to_min(state.memory.intent.hard_constraints.start_time)
    end_min = _hhmm_to_min(state.memory.intent.hard_constraints.end_time)
    weekday = _weekday_name(state.context.date)
    travel = _travel_matrix(repo_by_id, candidate_ids)

    nodes: list[OptwNode] = []
    for poi_id in candidate_ids:
        pool_poi = pool_by_id[poi_id]
        repo_poi = repo_by_id.get(poi_id)
        open_min, close_min = _opening_window(repo_poi, weekday, start_min, end_min)
        queue_min = int(
            pool_poi.estimated_queue_min
            or ((getattr(repo_poi, "queue_estimate", {}) or {}).get("weekend_peak", 0) if repo_poi else 0)
            or 0
        )
        nodes.append(
            OptwNode(
                poi_id=poi_id,
                category=pool_poi.category,
                utility=float(pool_poi.suitable_score or 0) * 100,
                visit_min=int(getattr(repo_poi, "visit_duration", 40) or 40),
                price=int(pool_poi.price_per_person or getattr(repo_poi, "price_per_person", 0) or 0),
                open_min=open_min,
                close_min=close_min,
                queue_min=queue_min,
            )
        )

    required_categories: set[str] = set()
    required_groups: list[set[str]] = []
    intent = state.memory.intent
    if intent.hard_constraints.must_include_meal:
        required_categories.add("restaurant")
    if intent.hard_constraints.must_include_experience:
        required_groups.append(set(EXPERIENCE_CATEGORIES))

    result = solve_optw(
        nodes,
        travel,
        start_min=start_min,
        end_min=end_min,
        budget=intent.hard_constraints.budget_total,
        must_visit=set(intent.must_visit_pois),
        required_categories=required_categories,
        required_category_groups=required_groups,
        max_stops=max_stops,
        time_limit_seconds=time_limit_seconds,
        solver_mode=solver_mode,
    )
    route_variants = [
        variant.to_dict()
        for variant in build_pareto_variants(
            _variant_candidate_nodes(nodes, result.ordered_ids),
            travel,
            solve_kwargs={
                "start_min": start_min,
                "end_min": end_min,
                "budget": intent.hard_constraints.budget_total,
                "must_visit": set(intent.must_visit_pois),
                "required_categories": required_categories,
                "required_category_groups": required_groups,
                "max_stops": max_stops,
                "time_limit_seconds": min(time_limit_seconds, PARETO_PROFILE_TIME_LIMIT_SECONDS),
                "solver_mode": solver_mode,
            },
        )
    ]

    if result.ordered_ids:
        pool.default_selected_ids = result.ordered_ids
    optimization = {
        "solver": result.solver,
        "objective_value": result.objective_value,
        "selected_utility": result.selected_utility,
        "constraint_violations": result.constraint_violations,
        "optimality_gap": result.optimality_gap,
        "fallback_used": result.fallback_used,
    }
    return ToolResult(
        observation_summary=(
            f"Solved constrained route with {result.solver}; "
            f"selected={len(result.ordered_ids)} utility={round(result.selected_utility, 2)}."
        ),
        payload=result.__dict__,
        memory_patch={"pool": pool, "route_optimization": optimization, "route_variants": route_variants},
        next_phase="COMPOSING",
    )


def _compose_story(state: AgentState, args: dict[str, Any]) -> ToolResult:
    agent = StoryAgent()
    story = agent.compose(state)
    if state.memory.route_optimization and story.optimization is None:
        story.optimization = RouteOptimizationSummary.model_validate(state.memory.route_optimization)
    if state.memory.robustness and story.robustness is None:
        story.robustness = RobustnessSummary.model_validate(state.memory.robustness)
    return ToolResult(
        observation_summary=(
            f"Composed story route '{story.theme}' with {len(story.stops)} stops "
            f"and {len(story.dropped)} dropped candidates."
        ),
        payload=story,
        memory_patch={"story_plan": story},
        next_phase="COMPOSING",
        observation_payload_ref=f"prompt:story@{agent.last_prompt_version}",
    )


def _parse_feedback(state: AgentState, args: dict[str, Any]) -> ToolResult:
    message = str(args.get("message") or state.goal.raw_query)
    intent = RepairAgent().parse(message)
    if intent.budget_per_person is not None:
        state.context.budget_per_person = intent.budget_per_person
        if state.memory.intent is not None:
            state.memory.intent.hard_constraints.budget_total = intent.budget_per_person
    return ToolResult(
        observation_summary=(
            f"Parsed feedback as {intent.event_type}; "
            f"deltas={', '.join(intent.deltas.keys()) or 'none'}."
        ),
        payload=intent,
        memory_patch={"feedback_intent": intent.model_dump()},
        next_phase="COMPOSING",
    )


def _replan_by_event(state: AgentState, args: dict[str, Any]) -> ToolResult:
    feedback = state.memory.feedback_intent or {}
    story = state.memory.story_plan
    if story is None:
        return ToolResult(
            observation_summary="No story route to adjust.",
            payload=None,
            memory_patch={"feedback_applied": True},
            next_phase="PRESENTING",
        )

    updated = story.model_copy(deep=True)
    current_ids = [stop.poi_id for stop in updated.stops]
    target_index = int(feedback.get("target_stop_index") or 0)
    target_index = max(0, min(target_index, len(updated.stops) - 1))
    replacement_budget = _replacement_budget(
        updated,
        target_index=target_index,
        budget=feedback.get("budget_per_person"),
    )
    replacement = _select_feedback_replacement(
        state,
        current_ids=set(current_ids),
        category_hint=feedback.get("category_hint"),
        budget=replacement_budget,
    )
    if replacement is not None and updated.stops:
        feedback["_original_poi_at_target"] = updated.stops[target_index].poi_id
        state.memory.feedback_intent = feedback
        updated.stops[target_index] = StoryStop(
            poi_id=replacement.id,
            role=updated.stops[target_index].role,
            why=(
                f"Adjusted from feedback; {replacement.name} matches "
                f"{feedback.get('category_hint') or replacement.category} and current constraints."
            ),
            ugc_quote_ref=f"pool:{replacement.id}",
            ugc_quote=replacement.highlight_quotes[0].quote if replacement.highlight_quotes else replacement.name,
            suggested_dwell_min=55 if replacement.category == "restaurant" else 40,
        )
    return ToolResult(
        observation_summary=(
            "Applied feedback to story route."
            if replacement is not None
            else "Feedback parsed but no better replacement was available."
        ),
        payload=updated,
        memory_patch={
            "story_plan": updated,
            "route_chain": None,
            "validation": None,
            "robustness": None,
            "critique": None,
            "feedback_intent": feedback,
            "feedback_applied": True,
        },
        next_phase="COMPOSING",
    )


def _get_amap_chain(state: AgentState, args: dict[str, Any]) -> ToolResult:
    story_ids = [stop.poi_id for stop in state.memory.story_plan.stops] if state.memory.story_plan else []
    pool_ids = state.memory.pool.default_selected_ids if state.memory.pool else []
    raw_ids = list(args.get("poi_ids") or story_ids or pool_ids)
    repo = get_poi_repository()
    poi_ids = _compact_route_ids(raw_ids, repo)
    story_patch = _story_with_ids(state, poi_ids) if poi_ids != raw_ids and state.memory.story_plan else None
    payload = RouteChainRequest(mode=AmapRouteMode(args.get("mode") or "driving"), poi_ids=poi_ids)
    route_pois = routes_route._resolve_route_pois(payload)
    client = routes_route.AmapRouteClient()
    try:
        route_chain = routes_route.build_route_chain(
            payload=payload,
            route_pois=route_pois,
            client=client,
        )
    finally:
        client.close()
    return ToolResult(
        observation_summary=(
            f"Built Amap route chain for {len(route_chain.ordered_pois)} POIs, "
            f"{round(route_chain.total_distance_m)} meters."
        ),
        payload=route_chain,
        memory_patch={
            "route_chain": route_chain,
            **({"story_plan": story_patch} if story_patch is not None else {}),
        },
        next_phase="PRESENTING",
    )


def _validate_route(state: AgentState, args: dict[str, Any]) -> ToolResult:
    if state.memory.intent is None:
        raise ValueError("Cannot validate route before intent is parsed")
    route = _story_route_skeleton(state)
    validation = RouteValidator().validate(
        route,
        state.memory.intent,
        state.context,
        state.profile,
    )
    return ToolResult(
        observation_summary=(
            "Route validation passed."
            if validation.is_valid
            else f"Route validation found {len(validation.issues)} issues."
        ),
        payload=validation,
        memory_patch={"validation": validation},
        next_phase="CHECKING",
    )


def _assess_robustness(state: AgentState, args: dict[str, Any]) -> ToolResult:
    route = _story_route_skeleton(state)
    poi_ids = [stop.poi_id for stop in route.stops]
    repo = get_poi_repository()
    queue_by_id = {
        poi.id: int((getattr(poi, "queue_estimate", {}) or {}).get("weekend_peak", 0) or 0)
        for poi in repo.get_many(poi_ids)
    }
    samples = int(args.get("samples") or 500)
    seed = int(args.get("seed") or 42)
    summary = simulate(
        route,
        queue_by_id,
        end_min=_hhmm_to_min(state.context.time_window.end),
        n=samples,
        seed=seed,
    )
    story_patch = state.memory.story_plan.model_copy(deep=True) if state.memory.story_plan else None
    if story_patch is not None:
        story_patch.robustness = summary
    return ToolResult(
        observation_summary=(
            f"Assessed route robustness: on_time_prob={summary.on_time_prob}, "
            f"p90_total_min={summary.p90_total_min}."
        ),
        payload=summary,
        memory_patch={
            "robustness": summary.model_dump(),
            **({"story_plan": story_patch} if story_patch is not None else {}),
        },
        next_phase="CHECKING",
    )


def _critique(state: AgentState, args: dict[str, Any]) -> ToolResult:
    critique = Critic().review(state)
    if (
        not critique.should_stop
        and state.goal.kind == "plan_route"
        and state.memory.story_plan is not None
        and state.memory.story_retry_count < 1
        and "time_budget_exceeded" in critique.issues
    ):
        compacted = _compact_story_for_time_budget(state)
        return ToolResult(
            observation_summary="Critic compacted route after time budget was exceeded.",
            payload=critique,
            memory_patch={
                "story_plan": compacted,
                "route_chain": None,
                "validation": None,
                "robustness": None,
                "critique": None,
                "story_retry_count": state.memory.story_retry_count + 1,
            },
            next_phase="COMPOSING",
        )
    if not critique.should_stop and state.goal.kind == "plan_route" and state.memory.story_retry_count < 1:
        if not _should_retry_story(critique.issues):
            return ToolResult(
                observation_summary=f"Critic requested revision: {', '.join(critique.issues)}",
                payload=critique,
                memory_patch={"critique": critique},
                next_phase="PRESENTING",
            )
        return ToolResult(
            observation_summary=f"Critic requested one story retry: {', '.join(critique.issues)}",
            payload=critique,
            memory_patch={
                "story_plan": None,
                "route_chain": None,
                "validation": None,
                "robustness": None,
                "critique": None,
                "story_retry_count": state.memory.story_retry_count + 1,
            },
            next_phase="COMPOSING",
        )
    return ToolResult(
        observation_summary=(
            "Critic approved the story route."
            if critique.should_stop
            else f"Critic requested revision: {', '.join(critique.issues)}"
        ),
        payload=critique,
        memory_patch={"critique": critique},
        next_phase="PRESENTING",
    )


def _story_route_skeleton(state: AgentState) -> RouteSkeleton:
    story_ids = [stop.poi_id for stop in state.memory.story_plan.stops] if state.memory.story_plan else []
    pool_ids = state.memory.pool.default_selected_ids if state.memory.pool else []
    poi_ids = story_ids or pool_ids[:5]
    repo = get_poi_repository()
    poi_by_id = {poi.id: poi for poi in repo.get_many(poi_ids)}
    route_chain = state.memory.route_chain
    segment_by_from = {segment.from_poi_id: segment for segment in route_chain.segments} if route_chain else {}

    current_time = state.context.time_window.start
    stops: list[RouteStop] = []
    total_transport_min = 0
    total_distance = 0
    queue_total = 0
    total_cost = 0

    for index, poi_id in enumerate(poi_ids):
        poi = poi_by_id.get(poi_id)
        dwell = _story_dwell_minutes(state, poi_id, poi)
        arrival = _wait_until_open(current_time, poi, state.context.date)
        departure = add_minutes(arrival, dwell)
        transport = None
        if index < len(poi_ids) - 1:
            segment = segment_by_from.get(poi_id)
            duration_min = int(round((segment.duration_s if segment else 900) / 60))
            distance_m = int(round(segment.distance_m if segment else 1200))
            transport = Transport(
                mode=route_chain.mode.value if route_chain else "driving",
                duration_min=duration_min,
                distance_meters=distance_m,
            )
            total_transport_min += duration_min
            total_distance += distance_m
            current_time = add_minutes(departure, duration_min)
        stops.append(
            RouteStop(
                poi_id=poi_id,
                arrival_time=arrival,
                departure_time=departure,
                duration_min=dwell,
                transport_to_next=transport,
            )
        )
        if poi:
            queue_total += poi.queue_estimate.get("weekend_peak", 0)
            total_cost += poi.price_per_person or 0

    total_duration = minutes_between(state.context.time_window.start, stops[-1].departure_time) if stops else 0
    return RouteSkeleton(
        style="story",
        stops=stops,
        dropped_poi_ids=[item.poi_id for item in state.memory.story_plan.dropped] if state.memory.story_plan else [],
        drop_reasons={item.poi_id: item.reason for item in state.memory.story_plan.dropped} if state.memory.story_plan else {},
        metrics=RouteMetrics(
            total_duration_min=total_duration,
            total_cost=total_cost,
            poi_count=len(stops),
            walking_distance_meters=total_distance,
            queue_total_min=queue_total,
        ),
    )


def _wait_until_open(current_time: str, poi: Any | None, date_value: str) -> str:
    if poi is None:
        return current_time
    current_min = _hhmm_to_min(current_time)
    open_min, _ = _opening_window(
        poi,
        _weekday_name(date_value),
        current_min,
        _hhmm_to_min("23:59"),
    )
    if open_min > current_min:
        return add_minutes("00:00", open_min)
    return current_time


def _story_dwell_minutes(state: AgentState, poi_id: str, poi: Any | None) -> int:
    if state.memory.story_plan:
        for stop in state.memory.story_plan.stops:
            if stop.poi_id == poi_id:
                return stop.suggested_dwell_min
    if poi and poi.category == "restaurant":
        return 55
    return 40


def _should_retry_story(issues: list[str]) -> bool:
    story_issue_codes = {
        "story_missing",
        "theme_missing",
        "narrative_missing",
        "invalid_stop_count",
        "weak_evidence",
        "hallucinated_poi",
        "hallucinated_ugc",
    }
    return any(issue in story_issue_codes for issue in issues)


def _compact_story_for_time_budget(state: AgentState):
    if state.memory.story_plan is None:
        return None
    story = state.memory.story_plan.model_copy(deep=True)
    if len(story.stops) <= 3:
        return story
    kept = story.stops[:3]
    dropped_ids = {stop.poi_id for stop in story.stops[3:]}
    story.stops = kept
    existing_dropped = {item.poi_id for item in story.dropped}
    for poi_id in dropped_ids - existing_dropped:
        story.dropped.append(type(story.dropped[0])(poi_id=poi_id, reason="time_budget_compaction") if story.dropped else _dropped_story_poi(poi_id))
    return story


def _dropped_story_poi(poi_id: str):
    from app.agent.story_models import DroppedStoryPoi

    return DroppedStoryPoi(poi_id=poi_id, reason="time_budget_compaction")


def _story_with_ids(state: AgentState, poi_ids: list[str]):
    if state.memory.story_plan is None:
        return None
    allowed = set(poi_ids)
    story = state.memory.story_plan.model_copy(deep=True)
    original = list(story.stops)
    story.stops = [stop for stop in original if stop.poi_id in allowed]
    dropped_ids = {stop.poi_id for stop in original if stop.poi_id not in allowed}
    existing_dropped = {item.poi_id for item in story.dropped}
    for poi_id in dropped_ids - existing_dropped:
        story.dropped.append(_dropped_story_poi(poi_id))
    return story


def _compact_route_ids(
    poi_ids: list[str],
    repo,
    *,
    max_stops: int = 4,
    max_segment_m: int = 8_000,
    max_total_m: int = 15_000,
) -> list[str]:
    ids = list(dict.fromkeys(poi_ids))
    if len(ids) <= 1:
        return ids
    poi_by_id = {poi.id: poi for poi in repo.get_many(ids)}
    if not poi_by_id:
        return ids[:max_stops]
    selected = [ids[0]]
    remaining = [poi_id for poi_id in ids[1:] if poi_id in poi_by_id]
    total_m = 0.0
    while remaining and len(selected) < max_stops:
        current = poi_by_id.get(selected[-1])
        if current is None:
            break
        options = [
            (haversine_meters(current, poi_by_id[poi_id]), poi_id)
            for poi_id in remaining
        ]
        options.sort(key=lambda item: item[0])
        next_item = next(
            (
                item
                for item in options
                if item[0] <= max_segment_m and total_m + item[0] <= max_total_m
            ),
            None,
        )
        if next_item is None:
            break
        distance_m, next_id = next_item
        selected.append(next_id)
        remaining.remove(next_id)
        total_m += distance_m
    if len(selected) >= 3:
        return selected
    return ids[: min(max_stops, len(ids))]


def _hhmm_to_min(value: str) -> int:
    return minutes_between("00:00", value)


def _weekday_name(date_value: str) -> str:
    try:
        return date_type.fromisoformat(date_value).strftime("%A").lower()
    except ValueError:
        return "saturday"


def _opening_window(poi: Any | None, weekday: str, start_min: int, end_min: int) -> tuple[int, int]:
    if poi is None:
        return start_min, end_min
    open_hours = getattr(poi, "open_hours", {}) or {}
    windows = open_hours.get(weekday, []) if isinstance(open_hours, dict) else []
    if not windows:
        return start_min, end_min
    first = windows[0]
    return _hhmm_to_min(first.get("open", "00:00")), _hhmm_to_min(first.get("close", "23:59"))


def _travel_matrix(repo_by_id: dict[str, Any], candidate_ids: list[str]) -> dict[tuple[str, str], int]:
    travel: dict[tuple[str, str], int] = {}
    for from_id in candidate_ids:
        for to_id in candidate_ids:
            if from_id == to_id:
                continue
            origin = repo_by_id.get(from_id)
            destination = repo_by_id.get(to_id)
            if origin is None or destination is None:
                travel[(from_id, to_id)] = 0
                continue
            if not all(
                hasattr(item, attr)
                for item in (origin, destination)
                for attr in ("latitude", "longitude")
            ):
                travel[(from_id, to_id)] = 0
                continue
            distance_m = haversine_meters(origin, destination)
            travel[(from_id, to_id)] = max(5, int(round(distance_m / 250)))
    return travel


def _variant_candidate_nodes(
    nodes: list[OptwNode],
    selected_ids: list[str],
    *,
    max_nodes: int = 8,
) -> list[OptwNode]:
    selected = [node for node in nodes if node.poi_id in set(selected_ids)]
    selected_set = {node.poi_id for node in selected}
    remaining = sorted(
        [node for node in nodes if node.poi_id not in selected_set],
        key=lambda node: node.utility,
        reverse=True,
    )
    return [*selected, *remaining[: max(0, max_nodes - len(selected))]]


def _select_feedback_replacement(
    state: AgentState,
    *,
    current_ids: set[str],
    category_hint: Any,
    budget: Any,
):
    if state.memory.pool is None:
        return None
    repo = get_poi_repository()
    pool_pois = [poi for category in state.memory.pool.categories for poi in category.pois]
    target_category = _target_category(str(category_hint or ""))
    options = [
        poi
        for poi in pool_pois
        if poi.id not in current_ids and (target_category is None or poi.category == target_category)
    ]
    if not options and target_category == "restaurant":
        options = [poi for poi in pool_pois if poi.id not in current_ids and poi.category == "restaurant"]
    if not options:
        options = [poi for poi in pool_pois if poi.id not in current_ids]
    if budget:
        options = [poi for poi in options if poi.price_per_person is None or poi.price_per_person <= int(budget)]
    if not options:
        return None
    options.sort(key=lambda poi: (-(poi.suitable_score or 0), poi.price_per_person or 9999))
    try:
        return repo.get(options[0].id)
    except KeyError:
        return None


def _target_category(category_hint: str) -> str | None:
    if category_hint in {"hotpot", "restaurant"}:
        return "restaurant"
    if category_hint in {"cafe", "culture", "nightlife", "scenic", "entertainment", "shopping", "outdoor"}:
        return category_hint
    return None


def _replacement_budget(story, *, target_index: int, budget: Any) -> int | None:
    if not budget:
        return None
    repo = get_poi_repository()
    total_other = 0
    for index, stop in enumerate(story.stops):
        if index == target_index:
            continue
        try:
            total_other += repo.get(stop.poi_id).price_per_person or 0
        except KeyError:
            continue
    return max(int(budget) - total_other, 0)

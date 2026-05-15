from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from app.agent import tool_schemas
from app.agent.state import AgentState
from app.agent.specialists.critic import Critic
from app.agent.specialists.repair_agent import RepairAgent
from app.agent.specialists.story_agent import StoryAgent
from app.agent.story_models import StoryStop
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
from app.services.pool_service import PoolService
from app.services.route_validator import RouteValidator
from app.utils.time_utils import add_minutes, minutes_between


class ToolResult(BaseModel):
    observation_summary: str
    payload: Any | None = None
    memory_patch: dict[str, Any] = Field(default_factory=dict)
    next_phase: str | None = None


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
            Tool("recommend_pool", tool_schemas.RECOMMEND_POOL, _recommend_pool),
            Tool("compose_story", tool_schemas.COMPOSE_STORY, _compose_story),
            Tool("get_amap_chain", tool_schemas.GET_AMAP_CHAIN, _get_amap_chain),
            Tool("parse_feedback", tool_schemas.PARSE_FEEDBACK, _parse_feedback),
            Tool("replan_by_event", tool_schemas.REPLAN_BY_EVENT, _replan_by_event),
            Tool("validate_route", tool_schemas.VALIDATE_ROUTE, _validate_route),
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
    if budget_total is not None and state.context.party == "couple":
        budget_total *= 2
    avoid_queue = any(keyword in free_text for keyword in ["少排队", "不排队", "排队少", "别排队"])
    photography = any(keyword in free_text for keyword in ["拍照", "打卡", "出片"])
    food = any(keyword in free_text for keyword in ["吃", "餐", "美食", "本地菜", "火锅"])
    pace = "efficient" if any(keyword in free_text for keyword in ["高效", "多逛", "多走"]) else "balanced"
    if any(keyword in free_text for keyword in ["轻松", "慢", "松弛"]):
        pace = "relaxed"
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
        avoid_pois=[],
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


def _compose_story(state: AgentState, args: dict[str, Any]) -> ToolResult:
    story = StoryAgent().compose(state)
    return ToolResult(
        observation_summary=(
            f"Composed story route '{story.theme}' with {len(story.stops)} stops "
            f"and {len(story.dropped)} dropped candidates."
        ),
        payload=story,
        memory_patch={"story_plan": story},
        next_phase="COMPOSING",
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
            "critique": None,
            "feedback_applied": True,
        },
        next_phase="COMPOSING",
    )


def _get_amap_chain(state: AgentState, args: dict[str, Any]) -> ToolResult:
    story_ids = [stop.poi_id for stop in state.memory.story_plan.stops] if state.memory.story_plan else []
    pool_ids = state.memory.pool.default_selected_ids if state.memory.pool else []
    poi_ids = list(args.get("poi_ids") or story_ids or pool_ids)[:5]
    payload = RouteChainRequest(mode=args.get("mode") or "driving", poi_ids=poi_ids)
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
        memory_patch={"route_chain": route_chain},
        next_phase="PRESENTING",
    )


def _validate_route(state: AgentState, args: dict[str, Any]) -> ToolResult:
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


def _critique(state: AgentState, args: dict[str, Any]) -> ToolResult:
    critique = Critic().review(state)
    if not critique.should_stop and state.goal.kind == "plan_route" and state.memory.story_retry_count < 1:
        return ToolResult(
            observation_summary=f"Critic requested one story retry: {', '.join(critique.issues)}",
            payload=critique,
            memory_patch={
                "story_plan": None,
                "route_chain": None,
                "validation": None,
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
        arrival = current_time
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


def _story_dwell_minutes(state: AgentState, poi_id: str, poi: Any | None) -> int:
    if state.memory.story_plan:
        for stop in state.memory.story_plan.stops:
            if stop.poi_id == poi_id:
                return stop.suggested_dwell_min
    if poi and poi.category == "restaurant":
        return 55
    return 40


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

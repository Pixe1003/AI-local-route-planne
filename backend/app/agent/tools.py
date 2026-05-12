from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from app.agent import tool_schemas
from app.agent.state import AgentState
from app.api import routes_route
from app.schemas.plan import HardConstraints, SoftPreferences, StructuredIntent
from app.schemas.pool import PoolRequest
from app.schemas.route import RouteChainRequest
from app.services.pool_service import PoolService


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
            Tool("recommend_pool", tool_schemas.RECOMMEND_POOL, _recommend_pool),
            Tool("get_amap_chain", tool_schemas.GET_AMAP_CHAIN, _get_amap_chain),
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
    pool = PoolService().generate_pool(request)
    if not pool.default_selected_ids and city != "shanghai":
        pool = PoolService().generate_pool(
            request.model_copy(update={"city": "shanghai", "need_profile": None})
        )
    return ToolResult(
        observation_summary=(
            f"Generated candidate pool with {pool.meta.total_count} POIs "
            f"and {len(pool.default_selected_ids)} default route ids."
        ),
        payload=pool,
        memory_patch={"pool": pool},
        next_phase="CHECKING",
    )


def _get_amap_chain(state: AgentState, args: dict[str, Any]) -> ToolResult:
    pool_ids = state.memory.pool.default_selected_ids if state.memory.pool else []
    poi_ids = list(args.get("poi_ids") or pool_ids)[:5]
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

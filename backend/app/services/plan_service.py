from uuid import uuid4

from app.repositories.poi_repo import get_poi_repository
from app.schemas.plan import (
    DroppedPoi,
    PlanContext,
    PlanRequest,
    PlanResponse,
    PlanSummary,
    RefinedPlan,
    RefinedStop,
    RouteSkeleton,
    StructuredIntent,
)
from app.services.intent_service import IntentService
from app.services.solver_service import SolverService
from app.services.state import PLAN_CONTEXT_REGISTRY, PLAN_REGISTRY
from app.services.ugc_service import UgcService
from app.solver.styles import STYLE_DESCRIPTIONS, STYLE_TITLES


class PlanService:
    def __init__(self) -> None:
        self.repo = get_poi_repository()
        self.ugc_service = UgcService()

    def generate_plans(self, request: PlanRequest) -> PlanResponse:
        intent = IntentService().parse_intent(
            "mock_user", request.selected_poi_ids, request.free_text, request.context
        )
        skeletons = SolverService().solve(intent, request.selected_poi_ids)
        return PlanResponse(plans=self.refine_plans(skeletons, intent, request.context))

    def refine_plans(
        self,
        skeletons: list[RouteSkeleton],
        intent: StructuredIntent,
        context: PlanContext,
    ) -> list[RefinedPlan]:
        plans = [self._refine_one(skeleton, intent, context) for skeleton in skeletons]
        for plan in plans:
            PLAN_REGISTRY[plan.plan_id] = plan
            PLAN_CONTEXT_REGISTRY[plan.plan_id] = context
        return plans

    def _refine_one(
        self, skeleton: RouteSkeleton, intent: StructuredIntent, context: PlanContext
    ) -> RefinedPlan:
        stops = []
        for stop in skeleton.stops:
            poi = self.repo.get(stop.poi_id)
            evidence = self.ugc_service.get_highlight_quotes(poi.id, intent.soft_preferences.custom_notes)
            queue = poi.queue_estimate["weekend_peak"]
            stops.append(
                RefinedStop(
                    poi_id=poi.id,
                    poi_name=poi.name,
                    arrival_time=stop.arrival_time,
                    departure_time=stop.departure_time,
                    why_this_one=f"{poi.name}匹配{context.party or '本次'}出行，UGC 高频提到{poi.high_freq_keywords[0]['keyword']}。",
                    ugc_evidence=evidence,
                    risk_warning="周末高峰可能排队，建议提前到达。" if queue > 40 else None,
                    transport_to_next=stop.transport_to_next,
                    latitude=poi.latitude,
                    longitude=poi.longitude,
                    category=poi.category,
                )
            )
        dropped = [
            DroppedPoi(
                poi_id=poi_id,
                poi_name=self.repo.get(poi_id).name,
                reason=skeleton.drop_reasons.get(poi_id, "时间窗不足"),
            )
            for poi_id in skeleton.dropped_poi_ids
            if poi_id in {poi.id for poi in self.repo.list_by_city(context.city)}
        ]
        plan = RefinedPlan(
            plan_id=f"plan_{uuid4().hex[:10]}",
            style=skeleton.style,
            title=STYLE_TITLES[skeleton.style],
            description=STYLE_DESCRIPTIONS[skeleton.style],
            stops=stops,
            summary=PlanSummary(
                total_duration_min=skeleton.metrics.total_duration_min,
                total_cost=skeleton.metrics.total_cost,
                poi_count=skeleton.metrics.poi_count,
                style_highlights=self._style_highlights(skeleton.style),
                tradeoffs=self._tradeoffs(skeleton.style, skeleton.metrics.poi_count),
                dropped_pois=dropped,
            ),
        )
        return plan

    def _style_highlights(self, style: str) -> list[str]:
        return {
            "efficient": ["站点更多", "覆盖经典地标", "适合第一次来上海"],
            "relaxed": ["排队更少", "停留更从容", "适合聊天散步"],
            "foodie_first": ["优先餐饮", "咖啡衔接", "晚餐时间更稳"],
        }[style]

    def _tradeoffs(self, style: str, poi_count: int) -> list[str]:
        if style == "efficient":
            return ["单点停留时间更紧", "对体力要求更高"]
        if style == "relaxed":
            return ["覆盖站点较少", "会放弃部分热门地标"]
        return ["文化和购物点减少", "总花费可能略高"]

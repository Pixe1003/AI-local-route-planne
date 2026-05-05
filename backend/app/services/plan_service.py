from uuid import uuid4

from app.repositories.poi_repo import get_poi_repository
from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import (
    PlanContext,
    DroppedPoi,
    PlanRequest,
    PlanResponse,
    PlanSummary,
    RefinedPlan,
    RefinedStop,
    RouteSkeleton,
    StructuredIntent,
)
from app.services.intent_service import IntentService
from app.services.poi_scoring_service import PoiScoringService
from app.services.route_validator import RouteValidator
from app.services.solver_service import SolverService
from app.services.state import (
    AgentRunState,
    PLAN_CONTEXT_REGISTRY,
    PLAN_PROFILE_REGISTRY,
    PLAN_REGISTRY,
    POOL_REGISTRY,
    register_run_state,
)
from app.services.ugc_service import UgcService
from app.solver.styles import STYLE_DESCRIPTIONS, STYLE_TITLES


class PlanService:
    def __init__(self) -> None:
        self.repo = get_poi_repository()
        self.ugc_service = UgcService()
        self.intent_service = IntentService()
        self.poi_scorer = PoiScoringService()
        self.validator = RouteValidator()

    def generate_plans(self, request: PlanRequest) -> PlanResponse:
        context = self._resolve_context(request)
        profile = self._resolve_profile(request, context)
        selected_poi_ids = self._resolve_selected_poi_ids(request)
        free_text = request.free_text or profile.raw_query
        run_state = register_run_state(
            AgentRunState(
                phase="UNDERSTANDING",
                user_need_profile=profile,
                context=context.model_dump(),
                candidate_poi_ids=selected_poi_ids,
                trace=["ONBOARDING", "UNDERSTANDING"],
            )
        )
        intent = self.intent_service.parse_intent(
            profile.user_id, selected_poi_ids, free_text, context
        )
        run_state.phase = "PLANNING"
        run_state.user_intent = intent.model_dump()
        skeletons = SolverService().solve(
            intent,
            selected_poi_ids,
            context=context,
            profile=profile,
        )
        run_state.candidate_routes = [skeleton.model_dump() for skeleton in skeletons]
        plans = self.refine_plans(skeletons, intent, context, profile)
        run_state.phase = "PRESENTING"
        run_state.selected_route_id = plans[0].plan_id if plans else None
        run_state.validation_result = plans[0].summary.validation if plans else None
        run_state.trace.extend(["PLANNING", "VALIDATING", "PRESENTING"])
        return PlanResponse(plans=plans)

    def refine_plans(
        self,
        skeletons: list[RouteSkeleton],
        intent: StructuredIntent,
        context: PlanContext,
        profile: UserNeedProfile | None = None,
    ) -> list[RefinedPlan]:
        profile = profile or UserNeedProfile.from_plan_context(context)
        plans = [self._refine_one(skeleton, intent, context, profile) for skeleton in skeletons]
        for plan in plans:
            PLAN_REGISTRY[plan.plan_id] = plan
            PLAN_CONTEXT_REGISTRY[plan.plan_id] = context
            PLAN_PROFILE_REGISTRY[plan.plan_id] = profile
        return plans

    def _refine_one(
        self,
        skeleton: RouteSkeleton,
        intent: StructuredIntent,
        context: PlanContext,
        profile: UserNeedProfile,
    ) -> RefinedPlan:
        stops = []
        for stop in skeleton.stops:
            poi = self.repo.get(stop.poi_id)
            evidence = self.ugc_service.get_highlight_quotes(poi.id, intent.soft_preferences.custom_notes)
            queue = poi.queue_estimate["weekend_peak"]
            score = self.poi_scorer.score_poi(
                poi,
                intent=intent,
                context=context,
                profile=profile,
                free_text=profile.raw_query,
            )
            strongest = self._strongest_score_factor(score.model_dump())
            stops.append(
                RefinedStop(
                    poi_id=poi.id,
                    poi_name=poi.name,
                    arrival_time=stop.arrival_time,
                    departure_time=stop.departure_time,
                    why_this_one=(
                        f"{poi.name}匹配{context.party or '本次'}出行。评分依据：{strongest}，"
                        f"UGC 高频提到{poi.high_freq_keywords[0]['keyword']}。"
                    ),
                    ugc_evidence=evidence,
                    risk_warning="周末高峰可能排队，建议提前到达。" if queue > 40 else None,
                    transport_to_next=stop.transport_to_next,
                    latitude=poi.latitude,
                    longitude=poi.longitude,
                    category=poi.category,
                    score_breakdown=score.model_dump(),
                    estimated_queue_min=queue,
                    estimated_cost=poi.price_per_person,
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
        validation = self.validator.validate(skeleton, intent, context, profile)
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
                total_queue_min=skeleton.metrics.queue_total_min,
                walking_distance_meters=skeleton.metrics.walking_distance_meters,
                validation=validation,
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

    def _resolve_context(self, request: PlanRequest) -> PlanContext:
        if request.context:
            return request.context
        if request.need_profile:
            return request.need_profile.to_plan_context()
        return PlanContext(
            city="shanghai",
            date="2026-05-02",
            time_window={"start": "13:00", "end": "21:00"},
            party="friends",
            budget_per_person=None,
        )

    def _resolve_profile(self, request: PlanRequest, context: PlanContext) -> UserNeedProfile:
        if request.need_profile:
            return request.need_profile
        return UserNeedProfile.from_plan_context(context, request.free_text)

    def _resolve_selected_poi_ids(self, request: PlanRequest) -> list[str]:
        if request.selected_poi_ids:
            return request.selected_poi_ids
        pool = POOL_REGISTRY.get(request.pool_id)
        return pool.default_selected_ids if pool else []

    def _strongest_score_factor(self, score: dict[str, float]) -> str:
        labels = {
            "user_interest": "用户兴趣匹配",
            "poi_quality": "POI 质量",
            "context_fit": "时间/人群适配",
            "ugc_match": "UGC 语义匹配",
            "service_closure": "消费闭环完整",
        }
        positive = {key: value for key, value in score.items() if key in labels}
        key = max(positive, key=positive.get)
        return f"{labels[key]} {positive[key]:.1f} 分"

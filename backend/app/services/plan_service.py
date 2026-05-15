from uuid import uuid4

from app.repositories.poi_repo import get_poi_repository
from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import (
    AlternativePoi,
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
from app.schemas.preferences import PreferenceSnapshot
from app.services.agent_skill_registry import get_agent_skill_registry
from app.services.intent_service import IntentService
from app.services.poi_scoring_service import PoiScoringService
from app.services.route_validator import RouteValidator
from app.services.solver_service import SolverService
from app.services.state import (
    AgentRunState,
    PLAN_CONTEXT_REGISTRY,
    PLAN_PREFERENCE_REGISTRY,
    PLAN_PROFILE_REGISTRY,
    PLAN_REGISTRY,
    POOL_REGISTRY,
    register_run_state,
)
from app.services.ugc_service import UgcService
from app.solver.styles import STYLE_DESCRIPTIONS, STYLE_TITLES


class PlanService:
    EXPERIENCE_CATEGORIES = {"culture", "scenic", "entertainment", "nightlife"}

    def __init__(self) -> None:
        self.agent_skill = get_agent_skill_registry().get_skill("route_planning")
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
            preference_snapshot=request.preference_snapshot,
        )
        run_state.candidate_routes = [skeleton.model_dump() for skeleton in skeletons]
        plans = self.refine_plans(skeletons, intent, context, profile, request.preference_snapshot)
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
        preference_snapshot: PreferenceSnapshot | None = None,
    ) -> list[RefinedPlan]:
        profile = profile or UserNeedProfile.from_plan_context(context)
        plans = [
            self._refine_one(skeleton, intent, context, profile, preference_snapshot)
            for skeleton in skeletons
        ]
        for plan in plans:
            PLAN_REGISTRY[plan.plan_id] = plan
            PLAN_CONTEXT_REGISTRY[plan.plan_id] = context
            PLAN_PROFILE_REGISTRY[plan.plan_id] = profile
            if preference_snapshot:
                PLAN_PREFERENCE_REGISTRY[plan.plan_id] = preference_snapshot
        return plans

    def _refine_one(
        self,
        skeleton: RouteSkeleton,
        intent: StructuredIntent,
        context: PlanContext,
        profile: UserNeedProfile,
        preference_snapshot: PreferenceSnapshot | None,
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
                preference_snapshot=preference_snapshot,
                free_text=profile.raw_query,
            )
            strongest = self._strongest_score_factor(score.model_dump())
            history_note = (
                "，也贴近你刚收藏的内容"
                if score.history_preference >= 8
                else ""
            )
            stops.append(
                RefinedStop(
                    poi_id=poi.id,
                    poi_name=poi.name,
                    arrival_time=stop.arrival_time,
                    departure_time=stop.departure_time,
                    why_this_one=(
                        f"{poi.name}匹配本次{context.party or '即时'}出行{history_note}。"
                        f"评分依据：{strongest}；UGC 高频提到{poi.high_freq_keywords[0]['keyword']}。"
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
        plan.alternative_pois = self._build_alternatives(plan, intent, context, profile, preference_snapshot)
        return plan

    def _build_alternatives(
        self,
        plan: RefinedPlan,
        intent: StructuredIntent,
        context: PlanContext,
        profile: UserNeedProfile,
        preference_snapshot: PreferenceSnapshot | None,
    ) -> list[AlternativePoi]:
        route_ids = {stop.poi_id for stop in plan.stops}
        candidate_ids = list(dict.fromkeys(
            [
                *(preference_snapshot.liked_poi_ids if preference_snapshot else []),
                *[dropped.poi_id for dropped in plan.summary.dropped_pois],
                *[poi.id for poi in self.repo.list_by_city(context.city)],
            ]
        ))
        alternatives: list[AlternativePoi] = []
        for poi_id in candidate_ids:
            if poi_id in route_ids:
                continue
            if poi_id not in {poi.id for poi in self.repo.list_by_city(context.city)}:
                continue
            poi = self.repo.get(poi_id)
            score = self.poi_scorer.score_poi(
                poi,
                intent=intent,
                context=context,
                profile=profile,
                preference_snapshot=preference_snapshot,
                free_text=profile.raw_query,
            )
            replace_index = self._replacement_index(plan, poi.category)
            old_stop = plan.stops[replace_index] if plan.stops else None
            old_poi = self.repo.get(old_stop.poi_id) if old_stop else None
            delta = 0
            if old_poi:
                delta = (poi.visit_duration + min(poi.queue_estimate["weekend_peak"], 30)) - (
                    old_poi.visit_duration + min(old_poi.queue_estimate["weekend_peak"], 30)
                )
            liked = preference_snapshot and poi.id in preference_snapshot.liked_poi_ids
            reason = self._alternative_reason(poi, score, liked, intent)
            alternatives.append(
                AlternativePoi(
                    poi_id=poi.id,
                    poi_name=poi.name,
                    category=poi.category,
                    replace_stop_index=replace_index,
                    why_candidate=reason,
                    delta_minutes=delta,
                    estimated_queue_min=poi.queue_estimate["weekend_peak"],
                    estimated_cost=poi.price_per_person,
                    score_breakdown=score.model_dump(),
                )
            )
        alternatives.sort(
            key=lambda item: (
                self._alternative_violates_constraints(item, intent),
                item.poi_id not in (preference_snapshot.liked_poi_ids if preference_snapshot else []),
                -item.score_breakdown.get("history_preference", 0),
                item.estimated_queue_min or 0,
                -(item.score_breakdown.get("total", 0)),
            )
        )
        return alternatives[:8]

    def _replacement_index(self, plan: RefinedPlan, category: str) -> int:
        for index, stop in enumerate(plan.stops):
            if stop.category == category:
                return index
        if category in self.EXPERIENCE_CATEGORIES:
            for index, stop in enumerate(plan.stops):
                if stop.category in self.EXPERIENCE_CATEGORIES:
                    return index
        return min(1, len(plan.stops) - 1) if plan.stops else 0

    def _alternative_reason(self, poi, score, liked: bool | None, intent: StructuredIntent) -> str:
        if liked and self._violates_main_route_preference(poi, intent):
            return "你收藏过它，但预算或排队压力偏高，先放在备选里，确认后可替换进路线。"
        if liked:
            return "你收藏过它，和历史偏好高度相关，可一键替换进路线。"
        if intent.soft_preferences.avoid_queue and poi.queue_estimate["weekend_peak"] <= 25:
            return "排队压力更低，适合临时替换。"
        strongest = self._strongest_score_factor(score.model_dump())
        return f"作为同区域备选，{strongest}，适合用户灵活调整。"

    def _violates_main_route_preference(self, poi, intent: StructuredIntent) -> bool:
        budget = intent.hard_constraints.budget_total
        if budget and poi.price_per_person and poi.price_per_person > budget:
            return True
        return intent.soft_preferences.avoid_queue and poi.queue_estimate["weekend_peak"] > 45

    def _alternative_violates_constraints(self, item: AlternativePoi, intent: StructuredIntent) -> bool:
        budget = intent.hard_constraints.budget_total
        if budget and item.estimated_cost and item.estimated_cost > budget:
            return True
        return bool(intent.soft_preferences.avoid_queue and (item.estimated_queue_min or 0) > 45)

    def _style_highlights(self, style: str) -> list[str]:
        return {
            "efficient": ["站点更多", "覆盖地标和体验点", "适合马上出发"],
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
            city="hefei",
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
            "history_preference": "收藏偏好匹配",
        }
        positive = {key: value for key, value in score.items() if key in labels}
        key = max(positive, key=positive.get)
        return f"{labels[key]} {positive[key]:.1f} 分"

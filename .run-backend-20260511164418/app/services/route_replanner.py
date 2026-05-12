from __future__ import annotations
from pydantic import BaseModel

from app.repositories.poi_repo import get_poi_repository
from app.schemas.plan import (
    RefinedPlan,
    RefinedStop,
    RouteMetrics,
    RouteSkeleton,
    RouteStop,
    UgcSnippet,
    ValidationResult,
)
from app.services.agent_skill_registry import get_agent_skill_registry
from app.services.poi_scoring_service import PoiScoringService
from app.services.route_validator import RouteValidator
from app.services.state import PLAN_CONTEXT_REGISTRY, PLAN_PROFILE_REGISTRY
from app.services.ugc_service import UgcService
from app.utils.time_utils import minutes_between


class ReplanEvent(BaseModel):
    event_type: str
    message: str | None = None
    target_poi_id: str | None = None
    target_stop_index: int | None = None
    replacement_poi_id: str | None = None


class ReplanResponse(BaseModel):
    event_type: str
    replan_level: str
    strategy: str
    plan: RefinedPlan
    assistant_message: str


class RouteReplanner:
    def __init__(self) -> None:
        self.agent_skill = get_agent_skill_registry().get_skill("replan")
        self.repo = get_poi_repository()
        self.ugc_service = UgcService()
        self.poi_scorer = PoiScoringService()
        self.validator = RouteValidator()

    def replan(self, plan: RefinedPlan, event: ReplanEvent) -> ReplanResponse:
        if event.event_type == "REPLACE_WITH_ALTERNATIVE":
            updated = self._replace_with_specific_poi(plan, event)
            level = "minor"
            strategy = "replace_with_user_selected_alternative"
            message = "已把你选中的备选 POI 替换进主路线，并重新校验可执行性。"
        elif event.event_type == "WEATHER_CHANGED":
            updated = self._replace_outdoor_stops(plan)
            level = "partial"
            strategy = "replace_weather_sensitive_pois"
            message = "已切换为雨天更稳的室内路线，并重新校验可执行性。"
        elif event.event_type == "BUDGET_EXCEEDED":
            updated = self._replace_expensive_stop(plan)
            level = "minor"
            strategy = "replace_expensive_poi"
            message = "已优先替换高价站点，降低本次路线预算压力。"
        elif event.event_type == "TIME_DELAYED":
            updated = self._compress_route(plan, event.message or "")
            level = "partial"
            strategy = "compress_remaining_route"
            message = "已压缩路线，保留更关键的站点并重新校验时间窗。"
        elif event.event_type == "USER_MODIFY_CONSTRAINT":
            updated = self._add_cafe(plan)
            level = "minor"
            strategy = "insert_rest_stop"
            message = "已加入一个低排队咖啡休息点，并保留原本主线。"
        else:
            updated = self._replace_high_queue_stop(plan, event)
            level = "minor"
            strategy = "replace_single_poi"
            message = "已替换为排队压力更低的同类选择，并重新校验路线。"
        updated.summary.validation = self._validate_plan(updated)
        return ReplanResponse(
            event_type=event.event_type,
            replan_level=level,
            strategy=strategy,
            plan=updated,
            assistant_message=message,
        )

    def _replace_with_specific_poi(self, plan: RefinedPlan, event: ReplanEvent) -> RefinedPlan:
        updated = plan.model_copy(deep=True)
        if event.replacement_poi_id is None or not updated.stops:
            return updated
        index = event.target_stop_index if event.target_stop_index is not None else 0
        index = max(0, min(index, len(updated.stops) - 1))
        replacement = self.repo.get(event.replacement_poi_id)
        updated.stops[index] = self._make_refined_stop(replacement, updated.stops[index])
        updated.summary.tradeoffs = ["已按用户选择替换单站，整体顺序保持不变。"]
        return self._refresh_summary(updated)

    def _replace_high_queue_stop(self, plan: RefinedPlan, event: ReplanEvent) -> RefinedPlan:
        updated = plan.model_copy(deep=True)
        if not updated.stops:
            return updated
        target_index = max(
            range(len(updated.stops)),
            key=lambda index: updated.stops[index].estimated_queue_min or 0,
        )
        if event.message and ("第二" in event.message or "2" in event.message) and len(updated.stops) > 1:
            target_index = 1
        old_stop = updated.stops[target_index]
        replacement = self.repo.find_replacement(
            exclude_ids={stop.poi_id for stop in updated.stops},
            category_hint=old_stop.category,
            avoid_queue=True,
        )
        if replacement is None:
            return updated
        updated.stops[target_index] = self._make_refined_stop(replacement, old_stop)
        updated.summary.tradeoffs = ["替换后保留原路线顺序，现场交通时间建议再刷新确认。"]
        return self._refresh_summary(updated)

    def _replace_outdoor_stops(self, plan: RefinedPlan) -> RefinedPlan:
        updated = plan.model_copy(deep=True)
        existing = {stop.poi_id for stop in updated.stops}
        for index, stop in enumerate(updated.stops):
            if stop.category != "outdoor":
                continue
            replacement = self.repo.find_replacement(
                exclude_ids=existing,
                category_hint="culture",
                avoid_queue=True,
            )
            if replacement:
                updated.stops[index] = self._make_refined_stop(replacement, stop)
                existing.add(replacement.id)
        updated.summary.tradeoffs = ["雨天方案减少户外暴露，文艺/商场/咖啡点权重提高。"]
        return self._refresh_summary(updated)

    def _replace_expensive_stop(self, plan: RefinedPlan) -> RefinedPlan:
        updated = plan.model_copy(deep=True)
        if not updated.stops:
            return updated
        target_index = max(
            range(len(updated.stops)),
            key=lambda index: updated.stops[index].estimated_cost or 0,
        )
        old_stop = updated.stops[target_index]
        replacement = self.repo.find_replacement(
            exclude_ids={stop.poi_id for stop in updated.stops},
            category_hint=old_stop.category,
            avoid_queue=False,
        )
        if replacement and (replacement.price_per_person or 0) < (old_stop.estimated_cost or 0):
            updated.stops[target_index] = self._make_refined_stop(replacement, old_stop)
        updated.summary.tradeoffs = ["省钱方案会优先降低高价站点，可能牺牲少量热度。"]
        return self._refresh_summary(updated)

    def _compress_route(self, plan: RefinedPlan, message: str) -> RefinedPlan:
        updated = plan.model_copy(deep=True)
        target_minutes = 120 if "2" in message or "两" in message else 180
        while len(updated.stops) > 3 and updated.summary.total_duration_min > target_minutes:
            updated.stops.pop()
            updated = self._refresh_summary(updated)
        updated.summary.tradeoffs = [f"已压缩到约 {updated.summary.total_duration_min} 分钟。"]
        return updated

    def _add_cafe(self, plan: RefinedPlan) -> RefinedPlan:
        updated = plan.model_copy(deep=True)
        cafe = self.repo.find_replacement(
            exclude_ids={stop.poi_id for stop in updated.stops},
            category_hint="cafe",
            avoid_queue=True,
        )
        if cafe is None:
            return updated
        anchor = updated.stops[0] if updated.stops else None
        arrival = anchor.departure_time if anchor else "15:00"
        new_stop = RefinedStop(
            poi_id=cafe.id,
            poi_name=cafe.name,
            arrival_time=arrival,
            departure_time=arrival,
            why_this_one=f"{cafe.name}低排队且适合中途休息。",
            ugc_evidence=[
                UgcSnippet(quote=f"{cafe.name}适合临时休息，下午更安静。", source="dianping")
            ],
            category=cafe.category,
            latitude=cafe.latitude,
            longitude=cafe.longitude,
            estimated_queue_min=cafe.queue_estimate["weekend_peak"],
            estimated_cost=cafe.price_per_person,
            score_breakdown=self.poi_scorer.score_poi(cafe).model_dump(),
        )
        updated.stops.insert(min(1, len(updated.stops)), new_stop)
        updated.summary.tradeoffs = ["加入咖啡后总时长略增，后续站点建议顺延。"]
        return self._refresh_summary(updated)

    def _make_refined_stop(self, poi, old_stop: RefinedStop) -> RefinedStop:
        score = self.poi_scorer.score_poi(poi)
        return RefinedStop(
            poi_id=poi.id,
            poi_name=poi.name,
            arrival_time=old_stop.arrival_time,
            departure_time=old_stop.departure_time,
            why_this_one=f"{poi.name}低排队/同类匹配，总分 {score.total:.1f}。",
            ugc_evidence=self.ugc_service.get_highlight_quotes(poi.id, [], 2),
            risk_warning=None,
            transport_to_next=old_stop.transport_to_next,
            latitude=poi.latitude,
            longitude=poi.longitude,
            category=poi.category,
            score_breakdown=score.model_dump(),
            estimated_queue_min=poi.queue_estimate["weekend_peak"],
            estimated_cost=poi.price_per_person,
        )

    def _refresh_summary(self, plan: RefinedPlan) -> RefinedPlan:
        plan.summary.poi_count = len(plan.stops)
        plan.summary.total_cost = sum(stop.estimated_cost or 0 for stop in plan.stops)
        plan.summary.total_queue_min = sum(stop.estimated_queue_min or 0 for stop in plan.stops)
        if plan.stops:
            plan.summary.total_duration_min = minutes_between(
                plan.stops[0].arrival_time, plan.stops[-1].departure_time
            )
        else:
            plan.summary.total_duration_min = 0
        return plan

    def _validate_plan(self, plan: RefinedPlan) -> ValidationResult:
        context = PLAN_CONTEXT_REGISTRY.get(plan.plan_id)
        profile = PLAN_PROFILE_REGISTRY.get(plan.plan_id)
        if context is None:
            return ValidationResult(is_valid=True)
        skeleton = RouteSkeleton(
            style=plan.style,
            stops=[
                RouteStop(
                    poi_id=stop.poi_id,
                    arrival_time=stop.arrival_time,
                    departure_time=stop.departure_time,
                    duration_min=minutes_between(stop.arrival_time, stop.departure_time),
                    transport_to_next=stop.transport_to_next,
                )
                for stop in plan.stops
            ],
            dropped_poi_ids=[dropped.poi_id for dropped in plan.summary.dropped_pois],
            drop_reasons={dropped.poi_id: dropped.reason for dropped in plan.summary.dropped_pois},
            metrics=RouteMetrics(
                total_duration_min=plan.summary.total_duration_min,
                total_cost=plan.summary.total_cost,
                poi_count=plan.summary.poi_count,
                walking_distance_meters=plan.summary.walking_distance_meters,
                queue_total_min=plan.summary.total_queue_min,
            ),
        )
        if profile is None:
            return ValidationResult(is_valid=True)
        from app.services.intent_service import IntentService

        intent = IntentService().parse_intent(
            profile.user_id,
            [stop.poi_id for stop in plan.stops],
            profile.raw_query,
            context,
        )
        return self.validator.validate(skeleton, intent, context, profile)


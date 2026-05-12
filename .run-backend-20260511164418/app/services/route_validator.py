from __future__ import annotations
from datetime import date as date_type

from app.repositories.poi_repo import get_poi_repository
from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import (
    PlanContext,
    RouteSkeleton,
    StructuredIntent,
    ValidationIssue,
    ValidationResult,
)
from app.utils.time_utils import minutes_between


class RouteValidator:
    EXPERIENCE_CATEGORIES = {"culture", "scenic", "entertainment", "nightlife"}

    def __init__(self) -> None:
        self.repo = get_poi_repository()

    def validate(
        self,
        route: RouteSkeleton,
        intent: StructuredIntent,
        context: PlanContext | None = None,
        profile: UserNeedProfile | None = None,
        repaired_count: int = 0,
    ) -> ValidationResult:
        issues: list[ValidationIssue] = []
        stop_ids = [stop.poi_id for stop in route.stops]
        pois = self.repo.get_many(stop_ids)
        poi_by_id = {poi.id: poi for poi in pois}
        route_categories = {poi.category for poi in pois}

        if len(route.stops) < 3:
            issues.append(ValidationIssue(code="too_few_pois", message="路线至少需要串联 3 个 POI。"))
        if "restaurant" not in route_categories:
            issues.append(ValidationIssue(code="meal_missing", message="路线需要包含至少 1 个餐饮点。"))
        if not route_categories & self.EXPERIENCE_CATEGORIES:
            issues.append(
                ValidationIssue(
                    code="experience_missing",
                    message="路线需要包含至少 1 个文化、娱乐、景点或夜景点。",
                )
            )

        for stop in route.stops:
            poi = poi_by_id.get(stop.poi_id)
            if poi is None:
                issues.append(
                    ValidationIssue(
                        code="poi_not_found",
                        message=f"{stop.poi_id} 不存在于 POI 数据源。",
                        target=stop.poi_id,
                    )
                )
                continue
            if context and not self._is_open(poi, context.date, stop.arrival_time):
                issues.append(
                    ValidationIssue(
                        code="poi_closed",
                        message=f"{poi.name} 在 {stop.arrival_time} 未营业。",
                        target=poi.id,
                    )
                )

        duration_budget = minutes_between(
            intent.hard_constraints.start_time, intent.hard_constraints.end_time
        )
        if route.metrics.total_duration_min > duration_budget:
            issues.append(
                ValidationIssue(
                    code="time_budget_exceeded",
                    message=f"路线总时长 {route.metrics.total_duration_min} 分钟超过 {duration_budget} 分钟时间窗。",
                )
            )

        if intent.hard_constraints.budget_total and route.metrics.total_cost > intent.hard_constraints.budget_total:
            issues.append(
                ValidationIssue(
                    code="budget_exceeded",
                    message=f"路线估算花费 {route.metrics.total_cost} 元超过预算 {intent.hard_constraints.budget_total} 元。",
                )
            )

        missing_must_visit = set(intent.must_visit_pois) - set(stop_ids) - set(route.dropped_poi_ids)
        for poi_id in missing_must_visit:
            issues.append(
                ValidationIssue(
                    code="must_visit_missing",
                    message=f"缺少用户必去点 {poi_id}。",
                    target=poi_id,
                )
            )

        queue_threshold = 45 if intent.soft_preferences.avoid_queue else 60
        if profile and "长时间排队" in profile.avoid:
            queue_threshold = 35
        for stop in route.stops:
            poi = poi_by_id.get(stop.poi_id)
            if poi and poi.queue_estimate["weekend_peak"] > queue_threshold:
                issues.append(
                    ValidationIssue(
                        code="queue_threshold_exceeded",
                        message=f"{poi.name} 排队预估 {poi.queue_estimate['weekend_peak']} 分钟超过阈值。",
                        target=poi.id,
                    )
                )

        return ValidationResult(
            is_valid=not any(issue.severity == "error" for issue in issues),
            issues=issues,
            repaired_count=repaired_count,
        )

    def _is_open(self, poi, date: str, arrival_time: str) -> bool:
        try:
            weekday = date_type.fromisoformat(date).strftime("%A").lower()
        except ValueError:
            weekday = "saturday"
        windows = poi.open_hours.get(weekday, []) if poi.open_hours else []
        return any(window["open"] <= arrival_time <= window["close"] for window in windows)


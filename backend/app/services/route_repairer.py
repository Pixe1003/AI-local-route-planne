from app.repositories.poi_repo import get_poi_repository
from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import RouteMetrics, RouteSkeleton, RouteStop, StructuredIntent
from app.services.route_validator import RouteValidator
from app.solver.distance import estimate_transport
from app.utils.time_utils import add_minutes, minutes_between


class RouteRepairer:
    def __init__(self) -> None:
        self.repo = get_poi_repository()
        self.validator = RouteValidator()

    def repair(
        self,
        route: RouteSkeleton,
        intent: StructuredIntent,
        *,
        context=None,
        profile: UserNeedProfile | None = None,
        max_iterations: int = 2,
    ) -> RouteSkeleton:
        current = route
        repaired_count = 0
        for _ in range(max_iterations):
            validation = self.validator.validate(current, intent, context, profile, repaired_count)
            if validation.is_valid:
                return current
            issue_codes = {issue.code for issue in validation.issues}
            if "time_budget_exceeded" in issue_codes:
                current = self._drop_until_time_fits(current, intent)
                repaired_count += 1
                continue
            if "budget_exceeded" in issue_codes:
                current = self._drop_until_budget_fits(current, intent)
                repaired_count += 1
                continue
            if "queue_threshold_exceeded" in issue_codes:
                current = self._replace_high_queue_stops(current, intent, profile)
                repaired_count += 1
                continue
            break
        return current

    def _drop_until_time_fits(
        self, route: RouteSkeleton, intent: StructuredIntent
    ) -> RouteSkeleton:
        current = route
        duration_budget = minutes_between(
            intent.hard_constraints.start_time, intent.hard_constraints.end_time
        )
        while len(current.stops) > 1 and current.metrics.total_duration_min > duration_budget:
            current = self._drop_last_stop(current, intent)
        return current

    def _drop_until_budget_fits(
        self, route: RouteSkeleton, intent: StructuredIntent
    ) -> RouteSkeleton:
        current = route
        budget = intent.hard_constraints.budget_total
        while budget and len(current.stops) > 1 and current.metrics.total_cost > budget:
            current = self._drop_most_expensive_stop(current, intent)
        return current

    def _drop_last_stop(self, route: RouteSkeleton, intent: StructuredIntent) -> RouteSkeleton:
        if len(route.stops) <= 1:
            return route
        kept_ids = [stop.poi_id for stop in route.stops[:-1]]
        dropped_id = route.stops[-1].poi_id
        return self._build_route(
            route.style,
            kept_ids,
            intent,
            route.dropped_poi_ids + [dropped_id],
            {**route.drop_reasons, dropped_id: "时间窗不足，自动压缩路线"},
        )

    def _drop_most_expensive_stop(
        self, route: RouteSkeleton, intent: StructuredIntent
    ) -> RouteSkeleton:
        if len(route.stops) <= 1:
            return route
        priced = [(self.repo.get(stop.poi_id).price_per_person or 0, stop.poi_id) for stop in route.stops]
        _, dropped_id = max(priced)
        kept_ids = [stop.poi_id for stop in route.stops if stop.poi_id != dropped_id]
        return self._build_route(
            route.style,
            kept_ids,
            intent,
            route.dropped_poi_ids + [dropped_id],
            {**route.drop_reasons, dropped_id: "超出预算，自动替换/删除高价站点"},
        )

    def _replace_high_queue_stops(
        self,
        route: RouteSkeleton,
        intent: StructuredIntent,
        profile: UserNeedProfile | None,
    ) -> RouteSkeleton:
        threshold = 35 if profile and "长时间排队" in profile.avoid else 45
        existing_ids = {stop.poi_id for stop in route.stops}
        next_ids: list[str] = []
        dropped = list(route.dropped_poi_ids)
        reasons = dict(route.drop_reasons)
        for stop in route.stops:
            poi = self.repo.get(stop.poi_id)
            if poi.queue_estimate["weekend_peak"] <= threshold:
                next_ids.append(stop.poi_id)
                continue
            replacement = self.repo.find_replacement(
                exclude_ids=existing_ids | set(next_ids),
                category_hint=poi.category,
                avoid_queue=True,
            )
            if replacement and replacement.queue_estimate["weekend_peak"] < poi.queue_estimate["weekend_peak"]:
                next_ids.append(replacement.id)
                dropped.append(poi.id)
                reasons[poi.id] = "排队超过阈值，替换为低排队同类站点"
            else:
                next_ids.append(stop.poi_id)
        return self._build_route(route.style, next_ids, intent, dropped, reasons)

    def _build_route(
        self,
        style: str,
        poi_ids: list[str],
        intent: StructuredIntent,
        dropped_poi_ids: list[str],
        drop_reasons: dict[str, str],
    ) -> RouteSkeleton:
        pois = self.repo.get_many(poi_ids)
        stops: list[RouteStop] = []
        current_time = intent.hard_constraints.start_time
        total_distance = 0
        queue_total = 0
        for index, poi in enumerate(pois):
            queue = poi.queue_estimate["weekend_peak"]
            duration = poi.visit_duration + min(queue, 30)
            arrival = current_time
            departure = add_minutes(arrival, duration)
            transport = None
            if index < len(pois) - 1:
                transport = estimate_transport(poi, pois[index + 1])
                total_distance += transport.distance_meters if transport.mode == "walking" else 0
                current_time = add_minutes(departure, transport.duration_min)
            stops.append(
                RouteStop(
                    poi_id=poi.id,
                    arrival_time=arrival,
                    departure_time=departure,
                    duration_min=duration,
                    transport_to_next=transport,
                )
            )
            queue_total += queue
        total_duration = minutes_between(
            intent.hard_constraints.start_time,
            stops[-1].departure_time if stops else intent.hard_constraints.start_time,
        )
        return RouteSkeleton(
            style=style,
            stops=stops,
            dropped_poi_ids=list(dict.fromkeys(dropped_poi_ids)),
            drop_reasons=drop_reasons,
            metrics=RouteMetrics(
                total_duration_min=total_duration,
                total_cost=sum(poi.price_per_person or 0 for poi in pois),
                poi_count=len(stops),
                walking_distance_meters=total_distance,
                queue_total_min=queue_total,
            ),
        )

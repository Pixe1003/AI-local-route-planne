from app.repositories.poi_repo import get_poi_repository
from app.repositories.poi_repo import PoiRepository
from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import RouteMetrics, RouteSkeleton, RouteStop, StructuredIntent
from app.schemas.preferences import PreferenceSnapshot
from app.services.category_policy import EXPERIENCE_CATEGORIES
from app.services.route_validator import RouteValidator
from app.solver.distance import estimate_transport
from app.utils.time_utils import add_minutes, minutes_between


class RouteRepairer:
    def __init__(self, repo: PoiRepository | None = None) -> None:
        self.repo = repo or get_poi_repository()
        self.validator = RouteValidator(repo=self.repo)
        self._city: str | None = None

    def repair(
        self,
        route: RouteSkeleton,
        intent: StructuredIntent,
        *,
        context=None,
        profile: UserNeedProfile | None = None,
        preference_snapshot: PreferenceSnapshot | None = None,
        max_iterations: int = 2,
    ) -> RouteSkeleton:
        # Thread the planning city so rebuilt legs can use the Amap transit
        # estimator (which short-circuits without a city) instead of always
        # falling back to haversine.
        self._city = getattr(context, "city", None)
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
        while len(current.stops) > 3 and current.metrics.total_duration_min > duration_budget:
            current = self._drop_last_stop(current, intent)
        if len(current.stops) >= 3 and current.metrics.total_duration_min > duration_budget:
            current = self._compress_stop_durations(current, intent, duration_budget)
        return current

    def _drop_until_budget_fits(
        self, route: RouteSkeleton, intent: StructuredIntent
    ) -> RouteSkeleton:
        current = route
        budget = intent.hard_constraints.budget_total
        while budget and len(current.stops) > 3 and current.metrics.total_cost > budget:
            current = self._drop_most_expensive_stop(current, intent)
        return current

    def _drop_last_stop(self, route: RouteSkeleton, intent: StructuredIntent) -> RouteSkeleton:
        if len(route.stops) <= 3:
            return route
        drop_index = self._time_drop_index(route, intent)
        dropped_id = route.stops[drop_index].poi_id
        kept_ids = [stop.poi_id for index, stop in enumerate(route.stops) if index != drop_index]
        return self._build_route(
            route.style,
            kept_ids,
            intent,
            route.dropped_poi_ids + [dropped_id],
            {**route.drop_reasons, dropped_id: "时间窗不足，自动压缩路线"},
        )

    def _time_drop_index(self, route: RouteSkeleton, intent: StructuredIntent) -> int:
        protected_ids = self._protected_stop_ids(route, intent)
        for index in range(len(route.stops) - 1, -1, -1):
            if route.stops[index].poi_id not in protected_ids:
                return index
        return len(route.stops) - 1

    def _protected_stop_ids(self, route: RouteSkeleton, intent: StructuredIntent) -> set[str]:
        pois = {poi.id: poi for poi in self.repo.get_many([stop.poi_id for stop in route.stops])}
        categories = [pois[stop.poi_id].category for stop in route.stops if stop.poi_id in pois]
        meal_count = categories.count("restaurant")
        experience_count = sum(1 for category in categories if category in EXPERIENCE_CATEGORIES)
        protected_ids: set[str] = set()
        for stop in route.stops:
            poi = pois.get(stop.poi_id)
            if poi is None:
                continue
            if (
                intent.hard_constraints.must_include_meal
                and poi.category == "restaurant"
                and meal_count <= 1
            ):
                protected_ids.add(stop.poi_id)
            if (
                intent.hard_constraints.must_include_experience
                and poi.category in EXPERIENCE_CATEGORIES
                and experience_count <= 1
            ):
                protected_ids.add(stop.poi_id)
        return protected_ids

    def _compress_stop_durations(
        self,
        route: RouteSkeleton,
        intent: StructuredIntent,
        duration_budget: int,
    ) -> RouteSkeleton:
        if not route.stops:
            return route
        transport_minutes = sum(
            stop.transport_to_next.duration_min
            for stop in route.stops
            if stop.transport_to_next is not None
        )
        available_visit = max(len(route.stops) * 5, duration_budget - transport_minutes)
        per_stop = max(5, available_visit // len(route.stops))
        current_time = intent.hard_constraints.start_time
        stops: list[RouteStop] = []
        for index, stop in enumerate(route.stops):
            arrival = current_time
            departure = add_minutes(arrival, per_stop)
            transport = stop.transport_to_next
            if index < len(route.stops) - 1 and transport is not None:
                current_time = add_minutes(departure, transport.duration_min)
            stops.append(
                RouteStop(
                    poi_id=stop.poi_id,
                    arrival_time=arrival,
                    departure_time=departure,
                    duration_min=per_stop,
                    transport_to_next=transport,
                )
            )
        total_duration = minutes_between(intent.hard_constraints.start_time, stops[-1].departure_time)
        return RouteSkeleton(
            style=route.style,
            stops=stops,
            dropped_poi_ids=route.dropped_poi_ids,
            drop_reasons=route.drop_reasons,
            metrics=RouteMetrics(
                total_duration_min=total_duration,
                total_cost=route.metrics.total_cost,
                poi_count=len(stops),
                walking_distance_meters=route.metrics.walking_distance_meters,
                queue_total_min=route.metrics.queue_total_min,
            ),
        )

    def _drop_most_expensive_stop(
        self, route: RouteSkeleton, intent: StructuredIntent
    ) -> RouteSkeleton:
        if len(route.stops) <= 3:
            return route
        protected_ids = self._protected_stop_ids(route, intent)
        priced = [
            (self.repo.get(stop.poi_id).price_per_person or 0, stop.poi_id)
            for stop in route.stops
            if stop.poi_id not in protected_ids
        ]
        if not priced:
            priced = [
                (self.repo.get(stop.poi_id).price_per_person or 0, stop.poi_id)
                for stop in route.stops
            ]
        _, dropped_id = max(priced)
        kept_ids = [stop.poi_id for stop in route.stops if stop.poi_id != dropped_id]
        return self._build_route(
            route.style,
            kept_ids,
            intent,
            route.dropped_poi_ids + [dropped_id],
            {**route.drop_reasons, dropped_id: "超出预算，自动删除高价站点"},
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
                transport = estimate_transport(poi, pois[index + 1], city=self._city)
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

from app.repositories.poi_repo import get_poi_repository
from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import RouteMetrics, RouteSkeleton, RouteStop, StructuredIntent
from app.services.route_repairer import RouteRepairer
from app.solver.distance import estimate_transport, haversine_meters
from app.solver.styles import PLAN_STYLES
from app.utils.time_utils import add_minutes, minutes_between


class SolverService:
    def __init__(self) -> None:
        self.repo = get_poi_repository()

    def solve(
        self,
        intent: StructuredIntent,
        candidate_poi_ids: list[str],
        *,
        context=None,
        profile: UserNeedProfile | None = None,
    ) -> list[RouteSkeleton]:
        ids = self._ensure_minimum_candidates(candidate_poi_ids)
        repairer = RouteRepairer()
        return [
            repairer.repair(
                self._solve_style(intent, ids, style),
                intent,
                context=context,
                profile=profile,
            )
            for style in PLAN_STYLES
        ]

    def _ensure_minimum_candidates(self, candidate_poi_ids: list[str]) -> list[str]:
        ids = list(dict.fromkeys(candidate_poi_ids))
        if len(ids) >= 5:
            return ids
        for poi in self.repo.list_by_city("shanghai"):
            if poi.id not in ids:
                ids.append(poi.id)
            if len(ids) >= 6:
                break
        return ids

    def _solve_style(
        self, intent: StructuredIntent, candidate_poi_ids: list[str], style: str
    ) -> RouteSkeleton:
        pois = self.repo.get_many(candidate_poi_ids)
        sorted_pois = sorted(pois, key=lambda poi: self._style_score(poi, style, intent), reverse=True)
        max_count = {"efficient": 6, "relaxed": 4, "foodie_first": 5}[style]
        route_pois = sorted_pois[:max(3, min(max_count, len(sorted_pois)))]
        if style == "efficient":
            route_pois = self._nearest_order(route_pois)
        elif style == "foodie_first":
            route_pois = sorted(route_pois, key=lambda poi: (poi.category != "restaurant", poi.category != "cafe"))
        else:
            route_pois = sorted(route_pois, key=lambda poi: (poi.queue_estimate["weekend_peak"], -poi.rating))

        stops: list[RouteStop] = []
        current_time = intent.hard_constraints.start_time
        total_distance = 0
        queue_total = 0
        for index, poi in enumerate(route_pois):
            queue = poi.queue_estimate["weekend_peak"]
            duration = poi.visit_duration + min(queue, 30)
            arrival = current_time
            departure = add_minutes(arrival, duration)
            transport = None
            if index < len(route_pois) - 1:
                transport = estimate_transport(poi, route_pois[index + 1])
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
        dropped = [poi_id for poi_id in candidate_poi_ids if poi_id not in {stop.poi_id for stop in stops}]
        return RouteSkeleton(
            style=style,
            stops=stops,
            dropped_poi_ids=dropped,
            drop_reasons={poi_id: "时间窗内优先保留更匹配的站点" for poi_id in dropped},
            metrics=RouteMetrics(
                total_duration_min=total_duration,
                total_cost=sum(poi.price_per_person or 0 for poi in route_pois),
                poi_count=len(stops),
                walking_distance_meters=total_distance,
                queue_total_min=queue_total,
            ),
        )

    def _style_score(self, poi, style: str, intent: StructuredIntent) -> float:
        score = poi.rating
        if style == "efficient":
            score += 0.6 if poi.category in {"scenic", "culture", "shopping"} else 0
            score += min(poi.review_count / 1000, 1)
        elif style == "relaxed":
            score += 1.0 if poi.queue_estimate["weekend_peak"] <= 25 else 0
            score += 0.7 if poi.category in {"cafe", "outdoor", "culture"} else 0
        else:
            score += 1.5 if poi.category == "restaurant" else 0
            score += 0.8 if poi.category == "cafe" else 0
        if intent.soft_preferences.photography_priority and "photogenic" in poi.atmosphere:
            score += 0.5
        return score

    def _nearest_order(self, pois):
        if not pois:
            return []
        ordered = [pois[0]]
        remaining = pois[1:]
        while remaining:
            current = ordered[-1]
            next_poi = min(remaining, key=lambda poi: haversine_meters(current, poi))
            ordered.append(next_poi)
            remaining.remove(next_poi)
        return ordered

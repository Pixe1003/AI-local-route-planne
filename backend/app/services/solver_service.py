from app.repositories.poi_repo import get_poi_repository
from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import RouteMetrics, RouteSkeleton, RouteStop, StructuredIntent
from app.schemas.preferences import PreferenceSnapshot
from app.services.poi_scoring_service import PoiScoringService
from app.services.route_repairer import RouteRepairer
from app.solver.distance import estimate_transport, haversine_meters
from app.solver.styles import PLAN_STYLES
from app.utils.time_utils import add_minutes, minutes_between


class SolverService:
    EXPERIENCE_CATEGORIES = {"culture", "scenic", "entertainment", "nightlife"}

    def __init__(self) -> None:
        self.repo = get_poi_repository()
        self.poi_scorer = PoiScoringService()

    def solve(
        self,
        intent: StructuredIntent,
        candidate_poi_ids: list[str],
        *,
        context=None,
        profile: UserNeedProfile | None = None,
        preference_snapshot: PreferenceSnapshot | None = None,
    ) -> list[RouteSkeleton]:
        ids = self._ensure_minimum_candidates(candidate_poi_ids, context.city if context else "hefei")
        repairer = RouteRepairer()
        return [
            repairer.repair(
                self._solve_style(intent, ids, style, profile, preference_snapshot),
                intent,
                context=context,
                profile=profile,
                preference_snapshot=preference_snapshot,
            )
            for style in PLAN_STYLES
        ]

    def _ensure_minimum_candidates(self, candidate_poi_ids: list[str], city: str) -> list[str]:
        ids = list(dict.fromkeys(candidate_poi_ids))
        city_pois = self.repo.list_by_city(city) or self.repo.list_by_city("hefei")
        categories = {self.repo.get(poi_id).category for poi_id in ids if poi_id in {poi.id for poi in city_pois}}
        if "restaurant" not in categories:
            self._append_first_category(ids, city_pois, {"restaurant"})
        if not categories & self.EXPERIENCE_CATEGORIES:
            self._append_first_category(ids, city_pois, self.EXPERIENCE_CATEGORIES)
        self._append_first_category(ids, city_pois, {"restaurant"})
        self._append_first_category(ids, city_pois, self.EXPERIENCE_CATEGORIES)
        self._append_first_category(ids, city_pois, {"cafe"})
        for poi in city_pois:
            if poi.id not in ids:
                ids.append(poi.id)
            if len(ids) >= 10:
                break
        return ids

    def _append_first_category(self, ids: list[str], pois, categories: set[str]) -> None:
        for poi in sorted(pois, key=lambda item: (item.price_per_person or 999, -item.rating)):
            if poi.category in categories and poi.id not in ids:
                ids.append(poi.id)
                return

    def _solve_style(
        self,
        intent: StructuredIntent,
        candidate_poi_ids: list[str],
        style: str,
        profile: UserNeedProfile | None,
        preference_snapshot: PreferenceSnapshot | None,
    ) -> RouteSkeleton:
        pois = [poi for poi in self.repo.get_many(candidate_poi_ids) if poi.id not in intent.avoid_pois]
        reasonable = [poi for poi in pois if self._reasonable_main_candidate(poi, intent)]
        if len(reasonable) >= 3:
            pois = reasonable
        sorted_pois = sorted(
            pois,
            key=lambda poi: self._style_score(poi, style, intent, profile, preference_snapshot),
            reverse=True,
        )
        max_count = {"efficient": 5, "relaxed": 4, "foodie_first": 4}[style]
        route_pois = sorted_pois[: max(3, min(max_count, len(sorted_pois)))]
        route_pois = self._ensure_route_coverage(route_pois, sorted_pois)
        route_pois = self._fit_budget(route_pois, sorted_pois, intent)
        if style == "efficient":
            route_pois = self._nearest_order(route_pois)
        elif style == "foodie_first":
            route_pois = sorted(route_pois, key=lambda poi: (poi.category != "restaurant", poi.category != "cafe"))
        else:
            route_pois = sorted(route_pois, key=lambda poi: (poi.queue_estimate["weekend_peak"], -poi.rating))
        return self._build_route(style, route_pois, intent, candidate_poi_ids)

    def _ensure_route_coverage(self, route_pois, sorted_pois):
        next_pois = list(route_pois)
        categories = {poi.category for poi in next_pois}
        if "restaurant" not in categories:
            self._replace_for_category(next_pois, sorted_pois, {"restaurant"})
        categories = {poi.category for poi in next_pois}
        if not categories & self.EXPERIENCE_CATEGORIES:
            self._replace_for_category(next_pois, sorted_pois, self.EXPERIENCE_CATEGORIES)
        return next_pois

    def _replace_for_category(self, route_pois, sorted_pois, categories: set[str]) -> None:
        replacement = next((poi for poi in sorted_pois if poi.category in categories and poi not in route_pois), None)
        if replacement is None:
            return
        for index in range(len(route_pois) - 1, -1, -1):
            if route_pois[index].category not in {"restaurant", *self.EXPERIENCE_CATEGORIES}:
                route_pois[index] = replacement
                return
        route_pois[-1] = replacement

    def _fit_budget(self, route_pois, sorted_pois, intent: StructuredIntent):
        budget = intent.hard_constraints.budget_total
        if not budget:
            return route_pois
        next_pois = list(route_pois)
        for _ in range(4):
            total = sum(poi.price_per_person or 0 for poi in next_pois)
            if total <= budget:
                return next_pois
            expensive_index = max(
                range(len(next_pois)),
                key=lambda index: next_pois[index].price_per_person or 0,
            )
            old = next_pois[expensive_index]
            category_options = {old.category}
            if old.category in self.EXPERIENCE_CATEGORIES:
                category_options = self.EXPERIENCE_CATEGORIES
            replacement = next(
                (
                    poi
                    for poi in sorted(sorted_pois, key=lambda item: (item.price_per_person or 999, -item.rating))
                    if poi.category in category_options
                    and poi not in next_pois
                    and (poi.price_per_person or 999) < (old.price_per_person or 999)
                ),
                None,
            )
            if replacement is None:
                return next_pois
            next_pois[expensive_index] = replacement
            next_pois = self._ensure_route_coverage(next_pois, sorted_pois)
        return next_pois

    def _build_route(
        self,
        style: str,
        route_pois,
        intent: StructuredIntent,
        candidate_poi_ids: list[str],
    ) -> RouteSkeleton:
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

    def _style_score(
        self,
        poi,
        style: str,
        intent: StructuredIntent,
        profile: UserNeedProfile | None,
        preference_snapshot: PreferenceSnapshot | None,
    ) -> float:
        score = poi.rating
        breakdown = self.poi_scorer.score_poi(
            poi,
            intent=intent,
            profile=profile,
            preference_snapshot=preference_snapshot,
            free_text=" ".join(intent.soft_preferences.custom_notes),
        )
        score += breakdown.total / 20
        if intent.hard_constraints.budget_total and poi.price_per_person:
            score -= max(0, poi.price_per_person - intent.hard_constraints.budget_total / 3) / 80
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

    def _reasonable_main_candidate(self, poi, intent: StructuredIntent) -> bool:
        budget = intent.hard_constraints.budget_total
        if budget and poi.price_per_person and poi.price_per_person > budget * 1.5:
            return False
        if intent.soft_preferences.avoid_queue and poi.queue_estimate["weekend_peak"] > 50:
            return False
        return True

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

from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.trip import RouteVersion, SaveRouteVersionRequest, TripRecord, TripSummary
from app.services.agent_skill_registry import get_agent_skill_registry
from app.services.state import TRIP_REGISTRY


class TripService:
    def __init__(self) -> None:
        self.agent_skill = get_agent_skill_registry().get_skill("trip_manager")

    def list_trips(self, user_id: str) -> list[TripSummary]:
        summaries = [
            trip.summary for trip in TRIP_REGISTRY.values() if trip.user_id == user_id
        ]
        return sorted(summaries, key=lambda summary: summary.updated_at, reverse=True)

    def get_trip(self, trip_id: str) -> TripRecord | None:
        return TRIP_REGISTRY.get(trip_id)

    def save_route_version(self, request: SaveRouteVersionRequest) -> TripRecord:
        if not request.plans:
            raise ValueError("plans cannot be empty")
        if request.active_plan_id not in {plan.plan_id for plan in request.plans}:
            raise ValueError("active_plan_id must reference one of the plans")

        created_at = datetime.now(timezone.utc)
        version = RouteVersion(
            version_id=f"version_{uuid4().hex[:10]}",
            plans=request.plans,
            active_plan_id=request.active_plan_id,
            source=request.source,
            created_at=created_at,
            user_message=request.user_message,
            pool_id=request.pool_id,
            selected_poi_ids=request.selected_poi_ids,
        )

        if request.trip_id:
            trip = TRIP_REGISTRY.get(request.trip_id)
            if trip is None:
                raise KeyError(request.trip_id)
            trip.profile = request.profile
            trip.planning_context = request.planning_context
            trip.versions.append(version)
            trip.active_version_id = version.version_id
            trip.summary = self._make_summary(trip, version)
        else:
            trip_id = f"trip_{uuid4().hex[:10]}"
            summary = self._make_summary_from_parts(
                trip_id=trip_id,
                profile=request.profile,
                version=version,
            )
            trip = TripRecord(
                trip_id=trip_id,
                user_id=request.user_id,
                profile=request.profile,
                planning_context=request.planning_context,
                versions=[version],
                active_version_id=version.version_id,
                summary=summary,
            )

        TRIP_REGISTRY[trip.trip_id] = trip
        return trip

    def _make_summary(self, trip: TripRecord, version: RouteVersion) -> TripSummary:
        return self._make_summary_from_parts(
            trip_id=trip.trip_id,
            profile=trip.profile,
            version=version,
            version_count=len(trip.versions),
        )

    def _make_summary_from_parts(
        self,
        trip_id: str,
        profile,
        version: RouteVersion,
        version_count: int = 1,
    ) -> TripSummary:
        active_plan = next(
            (plan for plan in version.plans if plan.plan_id == version.active_plan_id),
            version.plans[0],
        )
        cover_poi_names = [stop.poi_name for stop in active_plan.stops[:3]]
        city = profile.destination.city or "hefei"
        start_location = profile.destination.start_location
        party = profile.party_type or "friends"
        title_parts = [self._city_label(city), profile.date]
        if start_location:
            title_parts.append(f"从{start_location}出发")
        title_parts.append(self._party_label(party))
        return TripSummary(
            trip_id=trip_id,
            title=" · ".join(title_parts),
            city=city,
            date=profile.date,
            active_version_id=version.version_id,
            version_count=version_count,
            updated_at=version.created_at,
            cover_poi_names=cover_poi_names,
        )

    def _city_label(self, city: str) -> str:
        return {"hefei": "合肥", "shanghai": "上海", "nanjing": "南京"}.get(city, city)

    def _party_label(self, party: str) -> str:
        return {
            "couple": "情侣出行",
            "friends": "朋友聚会",
            "family": "亲子出行",
            "senior": "长辈友好",
            "solo": "独自出行",
        }.get(party, party)

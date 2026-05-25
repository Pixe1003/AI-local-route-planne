from typing import Protocol

from app.schemas.plan import PlanContext
from app.schemas.pool import PoolRequest
from app.schemas.rag import RetrievalQuery
from app.solver.distance import haversine_coordinate_meters


Origin = tuple[float, float]
DEFAULT_CITY_ORIGINS: dict[str, Origin] = {
    "hefei": (31.8206, 117.2272),
}


class _Located(Protocol):
    latitude: float
    longitude: float


def origin_from_query(query: RetrievalQuery) -> Origin | None:
    return _origin_from_values(query.origin_latitude, query.origin_longitude)


def origin_from_request(request: PoolRequest) -> Origin | None:
    explicit_origin = _origin_from_values(
        getattr(request, "origin_latitude", None),
        getattr(request, "origin_longitude", None),
    )
    if explicit_origin is not None:
        return explicit_origin

    destination = getattr(getattr(request, "need_profile", None), "destination", None)
    profile_origin = _origin_from_values(
        getattr(destination, "start_latitude", None),
        getattr(destination, "start_longitude", None),
    )
    if profile_origin is not None:
        return profile_origin

    return DEFAULT_CITY_ORIGINS.get(_city_from_request(request))


def radius_from_request(request: PoolRequest) -> int | None:
    explicit_radius = getattr(request, "radius_meters", None)
    if explicit_radius is not None:
        return explicit_radius

    destination = getattr(getattr(request, "need_profile", None), "destination", None)
    profile_radius = getattr(destination, "radius_meters", None)
    if profile_radius is not None:
        return profile_radius

    return None


def origin_from_context(context: PlanContext | None) -> Origin | None:
    if context is None:
        return None
    return _origin_from_values(
        getattr(context, "origin_latitude", None),
        getattr(context, "origin_longitude", None),
    )


def distance_from_origin(poi: _Located, origin: Origin | None) -> int | None:
    if origin is None:
        return None
    return haversine_coordinate_meters(origin[0], origin[1], poi.latitude, poi.longitude)


def within_radius(poi: _Located, origin: Origin | None, radius_meters: int | None) -> bool:
    if origin is None or radius_meters is None:
        return True
    distance = distance_from_origin(poi, origin)
    return distance is not None and distance <= radius_meters


def plan_context_from_pool_request(request: PoolRequest, city: str) -> PlanContext | None:
    origin = origin_from_request(request)
    if origin is None:
        return None
    return PlanContext(
        city=city,
        date=request.date,
        time_window=request.time_window,
        party=request.party,
        budget_per_person=request.budget_per_person,
        origin_latitude=origin[0],
        origin_longitude=origin[1],
        radius_meters=radius_from_request(request),
    )


def _city_from_request(request: PoolRequest) -> str:
    profile_city = getattr(getattr(getattr(request, "need_profile", None), "destination", None), "city", None)
    return str(profile_city or getattr(request, "city", "") or "")


def _origin_from_values(latitude: float | None, longitude: float | None) -> Origin | None:
    if latitude is None or longitude is None:
        return None
    return latitude, longitude

from typing import Protocol

from app.schemas.plan import PlanContext
from app.schemas.pool import PoolRequest
from app.schemas.rag import RetrievalQuery
from app.solver.distance import haversine_coordinate_meters


Origin = tuple[float, float]


class _Located(Protocol):
    latitude: float
    longitude: float


def origin_from_query(query: RetrievalQuery) -> Origin | None:
    return _origin_from_values(query.origin_latitude, query.origin_longitude)


def origin_from_request(request: PoolRequest) -> Origin | None:
    return _origin_from_values(request.origin_latitude, request.origin_longitude)


def origin_from_context(context: PlanContext | None) -> Origin | None:
    if context is None:
        return None
    return _origin_from_values(context.origin_latitude, context.origin_longitude)


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
    if origin_from_request(request) is None:
        return None
    return PlanContext(
        city=city,
        date=request.date,
        time_window=request.time_window,
        party=request.party,
        budget_per_person=request.budget_per_person,
        origin_latitude=request.origin_latitude,
        origin_longitude=request.origin_longitude,
        radius_meters=request.radius_meters,
    )


def _origin_from_values(latitude: float | None, longitude: float | None) -> Origin | None:
    if latitude is None or longitude is None:
        return None
    return latitude, longitude

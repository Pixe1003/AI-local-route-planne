from math import asin, cos, radians, sin, sqrt

from app.schemas.poi import PoiDetail
from app.schemas.plan import Transport
from app.solver import amap_client


def haversine_meters(a: PoiDetail, b: PoiDetail) -> int:
    return haversine_coordinate_meters(a.latitude, a.longitude, b.latitude, b.longitude)


def haversine_coordinate_meters(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> int:
    radius = 6_371_000
    dlat = radians(latitude_b - latitude_a)
    dlng = radians(longitude_b - longitude_a)
    lat1 = radians(latitude_a)
    lat2 = radians(latitude_b)
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return int(2 * radius * asin(sqrt(h)) * 1.3)


def _mode_for_distance(distance: int) -> str:
    if distance <= 1200:
        return "walking"
    if distance <= 4500:
        return "transit"
    return "driving"


def _haversine_transport(distance: int, mode: str) -> Transport:
    if mode == "walking":
        return Transport(mode="walking", duration_min=max(8, round(distance / 80)), distance_meters=distance)
    if mode == "transit":
        return Transport(mode="transit", duration_min=max(18, round(distance / 230)), distance_meters=distance)
    return Transport(mode="driving", duration_min=max(20, round(distance / 300)), distance_meters=distance)


def estimate_transport(a: PoiDetail, b: PoiDetail, *, city: str | None = None) -> Transport:
    """Estimate a single leg between two POIs.

    When an Amap key is configured the real walking/transit/driving leg is used;
    otherwise (and on any Amap error) we fall back to the deterministic
    haversine estimate so offline/test behaviour is unchanged.
    """
    distance = haversine_meters(a, b)
    mode = _mode_for_distance(distance)
    leg = amap_client.estimate_leg(mode, (a.latitude, a.longitude), (b.latitude, b.longitude), city)
    if leg is not None:
        duration_min, distance_meters = leg
        return Transport(mode=mode, duration_min=duration_min, distance_meters=distance_meters)
    return _haversine_transport(distance, mode)

from math import asin, cos, radians, sin, sqrt

from app.schemas.poi import PoiDetail
from app.schemas.plan import Transport


def haversine_meters(a: PoiDetail, b: PoiDetail) -> int:
    return haversine_coordinate_meters(a.latitude, a.longitude, b.latitude, b.longitude)


def haversine_coordinate_meters(
    origin_latitude: float,
    origin_longitude: float,
    destination_latitude: float,
    destination_longitude: float,
) -> int:
    radius = 6_371_000
    dlat = radians(destination_latitude - origin_latitude)
    dlng = radians(destination_longitude - origin_longitude)
    lat1 = radians(origin_latitude)
    lat2 = radians(destination_latitude)
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return int(2 * radius * asin(sqrt(h)) * 1.3)


def estimate_transport(a: PoiDetail, b: PoiDetail) -> Transport:
    distance = haversine_meters(a, b)
    if distance <= 1200:
        return Transport(mode="walking", duration_min=max(8, round(distance / 80)), distance_meters=distance)
    if distance <= 4500:
        return Transport(mode="transit", duration_min=max(18, round(distance / 230)), distance_meters=distance)
    return Transport(mode="driving", duration_min=max(20, round(distance / 300)), distance_meters=distance)

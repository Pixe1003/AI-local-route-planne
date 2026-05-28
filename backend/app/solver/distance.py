from math import asin, cos, radians, sin, sqrt
from typing import Literal

from app.schemas.poi import PoiDetail
from app.schemas.plan import Transport
from app.services.amap.client import AmapRouteClient
from app.services.amap.errors import AmapConfigError, AmapResponseParseError, AmapUpstreamError
from app.services.amap.schemas import AmapLngLat, AmapRouteMode


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
    amap_transport = _amap_transport(a, b)
    if amap_transport is not None:
        return amap_transport
    return _estimated_transport(a, b, source="fallback")


TransportSource = Literal["amap", "estimated", "fallback"]


def _estimated_transport(a: PoiDetail, b: PoiDetail, *, source: TransportSource = "estimated") -> Transport:
    distance = haversine_meters(a, b)
    if distance <= 1200:
        return Transport(
            mode="walking",
            duration_min=max(8, round(distance / 80)),
            distance_meters=distance,
            source=source,
        )
    if distance <= 4500:
        return Transport(
            mode="transit",
            duration_min=max(18, round(distance / 230)),
            distance_meters=distance,
            source=source,
        )
    return Transport(
        mode="driving",
        duration_min=max(20, round(distance / 300)),
        distance_meters=distance,
        source=source,
    )


def _amap_transport(a: PoiDetail, b: PoiDetail) -> Transport | None:
    estimated_distance = haversine_meters(a, b)
    mode = AmapRouteMode.WALKING if estimated_distance <= 1200 else AmapRouteMode.DRIVING
    client = None
    try:
        client = AmapRouteClient()
        result = client.get_route(
            mode=mode,
            origin=AmapLngLat(longitude=a.longitude, latitude=a.latitude),
            destination=AmapLngLat(longitude=b.longitude, latitude=b.latitude),
        )
    except (AmapConfigError, AmapUpstreamError, AmapResponseParseError):
        return None
    finally:
        if client is not None:
            client.close()
    duration_min = _duration_minutes(result.duration_s, result.distance_m, result.mode)
    return Transport(
        mode=result.mode.value,
        duration_min=duration_min,
        distance_meters=int(round(result.distance_m)),
        source="amap",
    )


def _duration_minutes(duration_s: float | None, distance_m: float, mode: AmapRouteMode) -> int:
    if duration_s is not None:
        return max(1, int(round(duration_s / 60)))
    divisor = 80 if mode == AmapRouteMode.WALKING else 300
    return max(1, int(round(distance_m / divisor)))

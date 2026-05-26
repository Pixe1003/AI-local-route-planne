"""Amap (高德) Direction API boundary used to estimate real travel legs.

The rest of the solver only ever asks for ``estimate_leg(...)`` and treats a
``None`` result as "Amap is unavailable, fall back to the haversine estimate".
This keeps the integration strictly opt-in: with no ``amap_key`` configured the
client short-circuits and the deterministic geometry path is used, so tests and
offline runs behave exactly as before.
"""

from functools import lru_cache
import logging
from typing import Optional

import httpx

from app.config import get_settings

Coordinate = tuple[float, float]  # (latitude, longitude)

logger = logging.getLogger(__name__)

_MODE_PATHS = {
    "walking": "/v3/direction/walking",
    "transit": "/v3/direction/transit/integrated",
    "driving": "/v3/direction/driving",
}


class AmapDirectionClient:
    """Thin, dependency-light wrapper over the Amap Direction REST API."""

    def __init__(
        self,
        *,
        key: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
    ) -> None:
        settings = get_settings()
        self.key = settings.amap_key if key is None else key
        self.base_url = (base_url or settings.amap_base_url).rstrip("/")
        self.timeout = settings.amap_timeout_seconds if timeout is None else timeout

    @property
    def enabled(self) -> bool:
        return bool(self.key)

    def leg(
        self,
        mode: str,
        origin: Coordinate,
        destination: Coordinate,
        city: str | None = None,
    ) -> Optional[tuple[int, int]]:
        """Return ``(duration_min, distance_meters)`` or ``None`` on any failure."""
        if not self.enabled:
            logger.info("Amap fallback: no api key configured")
            return None
        path = _MODE_PATHS.get(mode)
        if path is None:
            logger.info("Amap fallback: unsupported mode %s", mode)
            return None
        params = {
            "key": self.key,
            "origin": _format_point(origin),
            "destination": _format_point(destination),
        }
        if mode == "transit":
            # Amap's transit endpoint requires a city; without it we let the
            # caller fall back to the haversine estimate instead of guessing.
            if not city:
                logger.info("Amap fallback: transit city is required")
                return None
            params["city"] = city
            params["cityd"] = city
        try:
            response = httpx.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.warning("Amap direction call failed, using fallback: %s", exc)
            return None
        parsed = _parse_leg(mode, payload)
        if parsed is None:
            logger.info("Amap fallback: invalid direction response for mode %s", mode)
        return parsed


def _format_point(point: Coordinate) -> str:
    latitude, longitude = point
    # Amap expects "longitude,latitude" with up to 6 decimal places.
    return f"{longitude:.6f},{latitude:.6f}"


def _parse_leg(mode: str, payload: object) -> Optional[tuple[int, int]]:
    if not isinstance(payload, dict) or str(payload.get("status")) != "1":
        return None
    route = payload.get("route")
    if not isinstance(route, dict):
        return None
    if mode == "transit":
        legs = route.get("transits")
    else:
        legs = route.get("paths")
    if not isinstance(legs, list) or not legs:
        return None
    leg = legs[0]
    if not isinstance(leg, dict):
        return None
    try:
        duration_sec = float(leg.get("duration"))
        distance_m = float(leg.get("distance"))
    except (TypeError, ValueError):
        return None
    return max(1, round(duration_sec / 60)), max(0, round(distance_m))


@lru_cache(maxsize=4096)
def _cached_leg(
    mode: str,
    lat_a: float,
    lng_a: float,
    lat_b: float,
    lng_b: float,
    city: str | None,
) -> Optional[tuple[int, int]]:
    return AmapDirectionClient().leg(mode, (lat_a, lng_a), (lat_b, lng_b), city)


def estimate_leg(
    mode: str,
    origin: Coordinate,
    destination: Coordinate,
    city: str | None = None,
) -> Optional[tuple[int, int]]:
    """Cached Amap lookup keyed on coordinates rounded to ~1m precision."""
    return _cached_leg(
        mode,
        round(origin[0], 5),
        round(origin[1], 5),
        round(destination[0], 5),
        round(destination[1], 5),
        city or None,
    )


def clear_cache() -> None:
    """Drop memoised legs (used by tests that toggle the Amap key)."""
    _cached_leg.cache_clear()

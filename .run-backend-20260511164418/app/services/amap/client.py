from __future__ import annotations
from collections.abc import Mapping
from typing import Any
import os

import httpx

from app.config import get_settings
from app.services.amap.errors import (
    AmapConfigError,
    AmapResponseParseError,
    AmapUpstreamError,
)
from app.services.amap.polyline import parse_amap_polyline
from app.services.amap.schemas import (
    AmapLngLat,
    AmapRouteMode,
    AmapRouteResult,
    AmapRouteStep,
)


DEFAULT_AMAP_ROUTE_BASE_URL = "https://restapi.amap.com"
DEFAULT_AMAP_ROUTE_TIMEOUT_SECONDS = 15.0


class AmapRouteClient:
    _PATHS = {
        AmapRouteMode.WALKING: "/v5/direction/walking",
        AmapRouteMode.DRIVING: "/v5/direction/driving",
    }

    def __init__(
        self,
        *,
        key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        self.key = (
            key
            or os.getenv("AMAP_WEB_SERVICE_KEY")
            or os.getenv("AMAP_KEY")
            or settings.amap_web_service_key
            or settings.amap_key
        )
        if not self.key:
            raise AmapConfigError("AMAP_WEB_SERVICE_KEY or AMAP_KEY is required")

        self.base_url = (
            base_url
            or os.getenv("AMAP_ROUTE_BASE_URL")
            or settings.amap_route_base_url
            or DEFAULT_AMAP_ROUTE_BASE_URL
        )
        self.timeout_seconds = timeout_seconds or _read_timeout_seconds(settings)
        self._client = http_client or httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
        )
        self._owns_client = http_client is None

    def __enter__(self) -> "AmapRouteClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_route(
        self,
        *,
        mode: AmapRouteMode | str,
        origin: AmapLngLat,
        destination: AmapLngLat,
    ) -> AmapRouteResult:
        route_mode = AmapRouteMode(mode)
        try:
            response = self._client.get(
                self._PATHS[route_mode],
                params={
                    "key": self.key,
                    "origin": origin.to_amap_param(),
                    "destination": destination.to_amap_param(),
                    "show_fields": "cost,polyline,navi",
                },
            )
        except httpx.HTTPError as exc:
            raise AmapUpstreamError(info=str(exc), infocode=None, raw_response=None) from exc

        if response.status_code >= 400:
            raise AmapUpstreamError(
                info=f"HTTP {response.status_code}",
                infocode=str(response.status_code),
                raw_response=None,
            )

        raw_response = _response_json(response)
        if raw_response.get("status") != "1":
            raise AmapUpstreamError(
                info=_string_or_none(raw_response.get("info")),
                infocode=_string_or_none(raw_response.get("infocode")),
                raw_response=raw_response,
            )

        return _parse_route_result(raw_response=raw_response, mode=route_mode)


def _read_timeout_seconds(settings=None) -> float:
    raw_timeout = os.getenv("AMAP_ROUTE_TIMEOUT_SECONDS")
    if raw_timeout:
        try:
            return float(raw_timeout)
        except ValueError as exc:
            raise AmapConfigError("AMAP_ROUTE_TIMEOUT_SECONDS must be a number") from exc

    settings_timeout = getattr(settings, "amap_route_timeout_seconds", None)
    if settings_timeout is not None:
        try:
            return float(settings_timeout)
        except (TypeError, ValueError) as exc:
            raise AmapConfigError("AMAP_ROUTE_TIMEOUT_SECONDS must be a number") from exc

    return DEFAULT_AMAP_ROUTE_TIMEOUT_SECONDS


def _response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise AmapResponseParseError("Amap response is not valid JSON") from exc

    if not isinstance(data, dict):
        raise AmapResponseParseError("Amap response JSON must be an object")

    return data


def _parse_route_result(
    *,
    raw_response: dict[str, Any],
    mode: AmapRouteMode,
) -> AmapRouteResult:
    route = _mapping(raw_response.get("route"), "route")
    paths = route.get("paths")
    if not isinstance(paths, list) or not paths:
        raise AmapResponseParseError("Amap response route.paths must be a non-empty list")

    path = _mapping(paths[0], "route.paths[0]")
    steps_data = path.get("steps", [])
    if not isinstance(steps_data, list):
        raise AmapResponseParseError("Amap response route.paths[0].steps must be a list")

    steps = [_parse_step(step, index) for index, step in enumerate(steps_data)]
    polyline_coordinates: list[list[float]] = []
    for step in steps:
        polyline_coordinates.extend(step.polyline_coordinates)

    return AmapRouteResult(
        mode=mode,
        distance_m=_number(path.get("distance"), "route.paths[0].distance"),
        duration_s=_duration(path),
        steps=steps,
        polyline_coordinates=polyline_coordinates,
        raw_response=raw_response,
    )


def _parse_step(step_data: Any, index: int) -> AmapRouteStep:
    step = _mapping(step_data, f"route.paths[0].steps[{index}]")
    polyline = _string_or_none(step.get("polyline")) or ""

    try:
        polyline_coordinates = parse_amap_polyline(polyline)
    except AmapResponseParseError as exc:
        raise AmapResponseParseError(
            f"Failed to parse polyline for route.paths[0].steps[{index}]"
        ) from exc

    distance_value = step.get("distance", step.get("step_distance"))
    return AmapRouteStep(
        instruction=_string_or_none(step.get("instruction")),
        road_name=_string_or_none(step.get("road_name", step.get("road"))),
        distance_m=_number(distance_value, f"route.paths[0].steps[{index}].distance"),
        duration_s=_duration(step),
        polyline_coordinates=polyline_coordinates,
    )


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AmapResponseParseError(f"Amap response field {field_name} must be an object")
    return value


def _number(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise AmapResponseParseError(
            f"Amap response field {field_name} must be a number"
        ) from exc


def _duration(data: Mapping[str, Any]) -> float | None:
    if data.get("duration") is not None:
        return _number(data.get("duration"), "duration")

    cost = data.get("cost")
    if isinstance(cost, Mapping) and cost.get("duration") is not None:
        return _number(cost.get("duration"), "cost.duration")

    return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


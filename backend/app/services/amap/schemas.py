from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AmapRouteMode(StrEnum):
    WALKING = "walking"
    DRIVING = "driving"


class AmapLngLat(BaseModel):
    longitude: float
    latitude: float

    def to_amap_param(self) -> str:
        return f"{self.longitude},{self.latitude}"


class AmapRouteStep(BaseModel):
    instruction: str | None = None
    road_name: str | None = None
    distance_m: float
    duration_s: float | None = None
    polyline_coordinates: list[list[float]] = Field(default_factory=list)


class AmapRouteResult(BaseModel):
    mode: AmapRouteMode
    distance_m: float
    duration_s: float | None = None
    steps: list[AmapRouteStep] = Field(default_factory=list)
    polyline_coordinates: list[list[float]] = Field(default_factory=list)
    raw_response: dict[str, Any]

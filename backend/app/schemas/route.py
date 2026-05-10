from typing import Any, Literal

from pydantic import BaseModel, Field

from app.services.amap.schemas import AmapRouteMode


class RoutePoi(BaseModel):
    id: str
    name: str
    longitude: float
    latitude: float


class RouteChainRequest(BaseModel):
    mode: AmapRouteMode
    pois: list[RoutePoi]


class RouteSegmentSummary(BaseModel):
    segment_index: int
    from_poi_id: str
    from_poi_name: str
    to_poi_id: str
    to_poi_name: str
    distance_m: float
    duration_s: float


class RouteStepFeatureProperties(BaseModel):
    segment_index: int
    step_index: int
    from_poi_id: str
    from_poi_name: str
    to_poi_id: str
    to_poi_name: str
    instruction: str | None = None
    road_name: str | None = None
    distance_m: float
    duration_s: float | None = None


class GeoJSONLineString(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[list[float]]


class GeoJSONFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    properties: RouteStepFeatureProperties
    geometry: GeoJSONLineString


class GeoJSONFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[GeoJSONFeature] = Field(default_factory=list)


class RouteChainResponse(BaseModel):
    mode: AmapRouteMode
    ordered_pois: list[RoutePoi]
    total_distance_m: float
    total_duration_s: float
    segments: list[RouteSegmentSummary]
    geojson: GeoJSONFeatureCollection


ErrorDetail = dict[str, Any]

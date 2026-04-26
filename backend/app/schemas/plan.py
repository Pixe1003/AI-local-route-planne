from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.pool import TimeWindow


class PlanContext(BaseModel):
    city: str
    date: str
    time_window: TimeWindow
    party: Optional[str] = None
    budget_per_person: Optional[int] = None


class HardConstraints(BaseModel):
    start_time: str
    end_time: str
    budget_total: Optional[int] = None
    transport_mode: str = "mixed"
    must_include_meal: bool = False


class SoftPreferences(BaseModel):
    pace: str = "balanced"
    avoid_queue: bool = False
    weather_sensitive: bool = False
    photography_priority: bool = False
    food_diversity: bool = False
    custom_notes: list[str] = Field(default_factory=list)


class StructuredIntent(BaseModel):
    hard_constraints: HardConstraints
    soft_preferences: SoftPreferences
    must_visit_pois: list[str]
    avoid_pois: list[str] = Field(default_factory=list)


class Transport(BaseModel):
    mode: str
    duration_min: int
    distance_meters: int


class RouteStop(BaseModel):
    poi_id: str
    arrival_time: str
    departure_time: str
    duration_min: int
    transport_to_next: Optional[Transport] = None


class RouteMetrics(BaseModel):
    total_duration_min: int
    total_cost: int
    poi_count: int
    walking_distance_meters: int
    queue_total_min: int


class RouteSkeleton(BaseModel):
    style: str
    stops: list[RouteStop]
    dropped_poi_ids: list[str]
    drop_reasons: dict[str, str]
    metrics: RouteMetrics


class UgcSnippet(BaseModel):
    quote: str
    source: str
    date: Optional[str] = None


class RefinedStop(BaseModel):
    poi_id: str
    poi_name: str
    arrival_time: str
    departure_time: str
    why_this_one: str
    ugc_evidence: list[UgcSnippet]
    risk_warning: Optional[str] = None
    transport_to_next: Optional[Transport] = None
    latitude: float
    longitude: float
    category: str


class DroppedPoi(BaseModel):
    poi_id: str
    poi_name: str
    reason: str


class PlanSummary(BaseModel):
    total_duration_min: int
    total_cost: int
    poi_count: int
    style_highlights: list[str]
    tradeoffs: list[str]
    dropped_pois: list[DroppedPoi]


class RefinedPlan(BaseModel):
    plan_id: str
    style: str
    title: str
    description: str
    stops: list[RefinedStop]
    summary: PlanSummary


class PlanRequest(BaseModel):
    pool_id: str
    selected_poi_ids: list[str]
    free_text: Optional[str] = None
    context: PlanContext


class PlanResponse(BaseModel):
    plans: list[RefinedPlan]

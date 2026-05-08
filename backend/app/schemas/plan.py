from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.onboarding import UserNeedProfile
from app.schemas.pool import TimeWindow
from app.schemas.preferences import PreferenceSnapshot


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


class ScoreBreakdown(BaseModel):
    user_interest: float = 0.0
    poi_quality: float = 0.0
    context_fit: float = 0.0
    ugc_match: float = 0.0
    service_closure: float = 0.0
    history_preference: float = 0.0
    queue_penalty: float = 0.0
    price_penalty: float = 0.0
    distance_penalty: float = 0.0
    risk_penalty: float = 0.0
    total: float = 0.0


class ValidationIssue(BaseModel):
    code: str
    message: str
    severity: str = "error"
    target: Optional[str] = None


class ValidationResult(BaseModel):
    is_valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    repaired_count: int = 0


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
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    estimated_queue_min: Optional[int] = None
    estimated_cost: Optional[int] = None


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
    total_queue_min: int = 0
    walking_distance_meters: int = 0
    validation: ValidationResult = Field(default_factory=lambda: ValidationResult(is_valid=True))


class AlternativePoi(BaseModel):
    poi_id: str
    poi_name: str
    category: str
    replace_stop_index: Optional[int] = None
    why_candidate: str
    delta_minutes: int = 0
    estimated_queue_min: Optional[int] = None
    estimated_cost: Optional[int] = None
    score_breakdown: dict[str, float] = Field(default_factory=dict)


class RefinedPlan(BaseModel):
    plan_id: str
    style: str
    title: str
    description: str
    stops: list[RefinedStop]
    summary: PlanSummary
    alternative_pois: list[AlternativePoi] = Field(default_factory=list)


class PlanRequest(BaseModel):
    pool_id: str
    selected_poi_ids: list[str] = Field(default_factory=list)
    free_text: Optional[str] = None
    context: Optional[PlanContext] = None
    need_profile: Optional[UserNeedProfile] = None
    preference_snapshot: Optional[PreferenceSnapshot] = None


class PlanResponse(BaseModel):
    plans: list[RefinedPlan]

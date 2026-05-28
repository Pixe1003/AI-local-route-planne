from typing import Literal

from pydantic import BaseModel, Field


class RouteOptimizationSummary(BaseModel):
    solver: str
    objective_value: float = 0.0
    selected_utility: float = 0.0
    constraint_violations: list[str] = Field(default_factory=list)
    optimality_gap: float | None = None
    fallback_used: bool = False


class RobustnessSummary(BaseModel):
    on_time_prob: float
    expected_overflow_min: float
    p90_total_min: float
    samples: int


class StoryStop(BaseModel):
    poi_id: str
    role: Literal["opener", "midway", "main", "rest", "closer"]
    why: str
    ugc_quote_ref: str
    ugc_quote: str
    suggested_dwell_min: int = 45


class DroppedStoryPoi(BaseModel):
    poi_id: str
    reason: str


class StoryPlan(BaseModel):
    theme: str
    narrative: str
    stops: list[StoryStop]
    dropped: list[DroppedStoryPoi] = Field(default_factory=list)
    fallback_used: bool = False
    optimization: RouteOptimizationSummary | None = None
    robustness: RobustnessSummary | None = None

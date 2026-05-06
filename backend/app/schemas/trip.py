from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import PlanContext, RefinedPlan


class TripSummary(BaseModel):
    trip_id: str
    title: str
    city: str
    date: str
    active_version_id: str
    version_count: int
    updated_at: datetime
    cover_poi_names: list[str] = Field(default_factory=list)


class RouteVersion(BaseModel):
    version_id: str
    plans: list[RefinedPlan]
    active_plan_id: str
    source: str
    created_at: datetime
    user_message: Optional[str] = None
    pool_id: Optional[str] = None
    selected_poi_ids: list[str] = Field(default_factory=list)


class TripRecord(BaseModel):
    trip_id: str
    user_id: str
    profile: UserNeedProfile
    planning_context: PlanContext
    versions: list[RouteVersion] = Field(default_factory=list)
    active_version_id: str
    summary: TripSummary


class SaveRouteVersionRequest(BaseModel):
    trip_id: Optional[str] = None
    user_id: str
    profile: UserNeedProfile
    planning_context: PlanContext
    plans: list[RefinedPlan]
    active_plan_id: str
    pool_id: Optional[str] = None
    selected_poi_ids: list[str] = Field(default_factory=list)
    source: str
    user_message: Optional[str] = None

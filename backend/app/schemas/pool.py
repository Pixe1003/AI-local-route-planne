from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.onboarding import UserNeedProfile
from app.schemas.preferences import PreferenceSnapshot
from app.schemas.user_memory import UserFacts


class TimeWindow(BaseModel):
    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def validate_hhmm(cls, value: str) -> str:
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError("time must be HH:MM")
        hour, minute = int(parts[0]), int(parts[1])
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError("time must be HH:MM")
        return value


class PoolRequest(BaseModel):
    user_id: str
    city: str
    date: str = "2026-05-02"
    time_window: TimeWindow = Field(default_factory=lambda: TimeWindow(start="13:00", end="21:00"))
    persona_tags: list[str] = Field(default_factory=list)
    pace_style: Optional[str] = None
    party: Optional[str] = None
    budget_per_person: Optional[int] = None
    free_text: Optional[str] = None
    need_profile: Optional[UserNeedProfile] = None
    preference_snapshot: Optional[PreferenceSnapshot] = None
    user_facts: Optional[UserFacts] = None
    ugc_hits: list[dict[str, Any]] = Field(default_factory=list)


class PoiInPool(BaseModel):
    id: str
    name: str
    category: str
    rating: float
    price_per_person: Optional[int]
    cover_image: Optional[str]
    distance_meters: Optional[int]
    why_recommend: str
    highlight_quote: Optional[str]
    keywords: list[str]
    estimated_queue_min: Optional[int]
    suitable_score: float
    score_breakdown: dict[str, float] = Field(default_factory=dict)


class PoolCategory(BaseModel):
    name: str
    description: str
    pois: list[PoiInPool]


class PoolMeta(BaseModel):
    total_count: int
    generated_at: datetime
    user_persona_summary: str


class PoolResponse(BaseModel):
    pool_id: str
    categories: list[PoolCategory]
    default_selected_ids: list[str]
    meta: PoolMeta

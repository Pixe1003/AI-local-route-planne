from typing import Literal

from pydantic import BaseModel, Field


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

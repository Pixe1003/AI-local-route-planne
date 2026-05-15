from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.plan import RefinedPlan


class ChatTurn(BaseModel):
    role: str
    content: str
    timestamp: datetime


class ChatResponse(BaseModel):
    intent_type: str
    updated_plan: Optional[RefinedPlan]
    assistant_message: str
    requires_confirmation: bool
    event_type: Optional[str] = None
    replan_level: Optional[str] = None
    recommended_poi_ids: list[str] = Field(default_factory=list)
    alternative_poi_ids: list[str] = Field(default_factory=list)

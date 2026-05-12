from __future__ import annotations
from typing import Any, Optional

from pydantic import BaseModel, Field


class DestinationProfile(BaseModel):
    city: str = "shanghai"
    start_location: Optional[str] = None
    target_area: Optional[str] = None
    end_location: Optional[str] = None


class TimeProfile(BaseModel):
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    time_budget_minutes: Optional[int] = None


class BudgetProfile(BaseModel):
    budget_per_person: Optional[int] = None
    strict: bool = False


class UserNeedProfile(BaseModel):
    user_id: str = "mock_user"
    destination: DestinationProfile = Field(default_factory=DestinationProfile)
    time: TimeProfile = Field(default_factory=TimeProfile)
    date: str = "2026-05-02"
    activity_preferences: list[str] = Field(default_factory=list)
    food_preferences: list[str] = Field(default_factory=list)
    taste_preferences: list[str] = Field(default_factory=list)
    party_type: Optional[str] = None
    budget: BudgetProfile = Field(default_factory=BudgetProfile)
    route_style: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    must_visit: list[str] = Field(default_factory=list)
    must_avoid: list[str] = Field(default_factory=list)
    completeness_score: float = 0.0
    raw_query: Optional[str] = None

    @classmethod
    def from_plan_context(cls, context: Any, raw_query: str | None = None) -> "UserNeedProfile":
        return cls(
            destination=DestinationProfile(city=context.city),
            time=TimeProfile(
                start_time=context.time_window.start,
                end_time=context.time_window.end,
                time_budget_minutes=None,
            ),
            date=context.date,
            party_type=context.party,
            budget=BudgetProfile(budget_per_person=context.budget_per_person),
            raw_query=raw_query,
            completeness_score=0.8,
        )

    def to_plan_context(self):
        from app.schemas.plan import PlanContext
        from app.schemas.pool import TimeWindow

        return PlanContext(
            city=self.destination.city or "shanghai",
            date=self.date,
            time_window=TimeWindow(
                start=self.time.start_time or "13:00",
                end=self.time.end_time or "21:00",
            ),
            party=self.party_type,
            budget_per_person=self.budget.budget_per_person,
        )


class SuggestedQuestion(BaseModel):
    slot: str
    question: str
    options: list[str] = Field(default_factory=list)


class OnboardingAnalyzeRequest(BaseModel):
    query: str
    user_id: str = "mock_user"


class OnboardingAnalyzeResponse(BaseModel):
    completeness_score: float
    missing_slots: list[str]
    suggested_questions: list[str]
    can_plan: bool
    should_ask_followup: bool
    extracted_profile: UserNeedProfile


class OnboardingProfileRequest(BaseModel):
    query: str
    user_id: str = "mock_user"
    answers: dict[str, Any] = Field(default_factory=dict)


class OnboardingProfileResponse(BaseModel):
    profile: UserNeedProfile


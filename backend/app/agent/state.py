from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.agent.story_models import StoryPlan
from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import PlanContext, StructuredIntent
from app.schemas.pool import PoolResponse
from app.schemas.preferences import PreferenceSnapshot
from app.schemas.route import RouteChainResponse


class AgentGoal(BaseModel):
    kind: Literal["plan_route", "adjust_route", "explain_route", "explore_more"] = "plan_route"
    raw_query: str
    session_id: str = Field(default_factory=lambda: uuid4().hex)
    user_id: str
    locale_city: str = "hefei"


class ToolCall(BaseModel):
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None
    observation_summary: str | None = None
    observation_payload_ref: str | None = None
    error: str | None = None
    latency_ms: int = 0
    tokens_used: int = 0


class Critique(BaseModel):
    theme_coherence: int = 0
    evidence_strength: int = 0
    pacing: int = 0
    preference_fit: int = 0
    narrative: int = 0
    should_stop: bool = True
    hint: str | None = None
    issues: list[str] = Field(default_factory=list)


class AgentMemory(BaseModel):
    pool: PoolResponse | None = None
    intent: StructuredIntent | None = None
    route_chain: RouteChainResponse | None = None
    validation: Any | None = None
    critique: Critique | None = None
    ugc_hits: list[dict[str, Any]] = Field(default_factory=list)
    ugc_searched: bool = False
    story_plan: StoryPlan | None = None
    story_retry_count: int = 0
    feedback_intent: dict[str, Any] | None = None
    feedback_applied: bool = False


class AgentState(BaseModel):
    goal: AgentGoal
    profile: UserNeedProfile
    preference: PreferenceSnapshot | None = None
    context: PlanContext
    steps: list[ToolCall] = Field(default_factory=list)
    memory: AgentMemory = Field(default_factory=AgentMemory)
    phase: Literal[
        "UNDERSTANDING",
        "RETRIEVING",
        "COMPOSING",
        "CHECKING",
        "PRESENTING",
        "DONE",
        "FAILED",
    ] = "UNDERSTANDING"
    version: int = 1
    trace_id: str = Field(default_factory=lambda: uuid4().hex)

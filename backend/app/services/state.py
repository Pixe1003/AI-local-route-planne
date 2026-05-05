from uuid import uuid4

from pydantic import BaseModel, Field

from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import PlanContext, RefinedPlan, ValidationResult
from app.schemas.pool import PoolResponse


class AgentRunState(BaseModel):
    run_id: str = Field(default_factory=lambda: f"run_{uuid4().hex[:10]}")
    session_id: str = "session_demo"
    phase: str = "IDLE"
    user_need_profile: UserNeedProfile | None = None
    user_intent: dict = Field(default_factory=dict)
    context: dict = Field(default_factory=dict)
    candidate_poi_ids: list[str] = Field(default_factory=list)
    scored_pois: list[dict] = Field(default_factory=list)
    candidate_routes: list[dict] = Field(default_factory=list)
    selected_route_id: str | None = None
    validation_result: ValidationResult | None = None
    events: list[dict] = Field(default_factory=list)
    replan_level: str | None = None
    iteration_count: int = 0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)


POOL_REGISTRY: dict[str, PoolResponse] = {}
PLAN_REGISTRY: dict[str, RefinedPlan] = {}
PLAN_CONTEXT_REGISTRY: dict[str, PlanContext] = {}
PLAN_PROFILE_REGISTRY: dict[str, UserNeedProfile] = {}
RUN_STATE_REGISTRY: dict[str, AgentRunState] = {}


def register_run_state(state: AgentRunState) -> AgentRunState:
    RUN_STATE_REGISTRY[state.run_id] = state
    return state

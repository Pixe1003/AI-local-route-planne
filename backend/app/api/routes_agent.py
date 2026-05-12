from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent.conductor import Conductor
from app.agent.state import AgentGoal, AgentState, ToolCall
from app.agent.store import load_state, save_state
from app.agent.tools import get_tool_registry
from app.llm.client import LlmClient
from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import PlanContext
from app.schemas.pool import PoolResponse, TimeWindow
from app.schemas.preferences import PreferenceSnapshot
from app.schemas.route import RouteChainResponse


router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRunRequest(BaseModel):
    user_id: str
    free_text: str
    city: str = "hefei"
    time_window: TimeWindow
    date: str
    budget_per_person: int | None = None
    preference_snapshot: PreferenceSnapshot | None = None
    session_id: str | None = None
    parent_session_id: str | None = None


class AgentRunResponse(BaseModel):
    session_id: str
    trace_id: str
    phase: str
    ordered_poi_ids: list[str] = Field(default_factory=list)
    pool: PoolResponse | None = None
    route_chain: RouteChainResponse | None = None
    steps: list[ToolCall] = Field(default_factory=list)


@router.post("/run", response_model=AgentRunResponse)
def run_agent(request: AgentRunRequest) -> AgentRunResponse:
    state = build_initial_state(request)
    final = Conductor(get_tool_registry(), LlmClient()).run(state)
    save_state(final)
    return _response_from_state(final)


@router.get("/trace/{session_id}", response_model=AgentRunResponse)
def get_trace(session_id: str) -> AgentRunResponse:
    state = load_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Agent session not found")
    return _response_from_state(state)


def build_initial_state(request: AgentRunRequest) -> AgentState:
    session_id = request.session_id or uuid4().hex
    context = PlanContext(
        city=request.city,
        date=request.date,
        time_window=request.time_window,
        party="friends",
        budget_per_person=request.budget_per_person,
    )
    profile = UserNeedProfile.from_plan_context(context, raw_query=request.free_text)
    profile.user_id = request.user_id
    return AgentState(
        goal=AgentGoal(
            kind="plan_route",
            raw_query=request.free_text,
            session_id=session_id,
            user_id=request.user_id,
            locale_city=request.city,
        ),
        profile=profile,
        preference=request.preference_snapshot,
        context=context,
    )


def _response_from_state(state: AgentState) -> AgentRunResponse:
    route_chain = state.memory.route_chain
    ordered_poi_ids = [poi.id for poi in route_chain.ordered_pois] if route_chain else []
    return AgentRunResponse(
        session_id=state.goal.session_id,
        trace_id=state.trace_id,
        phase=state.phase,
        ordered_poi_ids=ordered_poi_ids,
        pool=state.memory.pool,
        route_chain=route_chain,
        steps=state.steps,
    )


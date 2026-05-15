from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.conductor import Conductor
from app.agent.state import AgentGoal, AgentState, Critique, ToolCall
from app.agent.story_models import StoryPlan
from app.agent.store import load_state, save_state
from app.agent.tools import get_tool_registry
from app.agent.tracing import format_sse, get_trace_events
from app.llm.client import LlmClient
from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import PlanContext, ValidationResult
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


class AgentAdjustRequest(BaseModel):
    parent_session_id: str
    user_message: str
    session_id: str | None = None


class AgentRunResponse(BaseModel):
    session_id: str
    trace_id: str
    phase: str
    ordered_poi_ids: list[str] = Field(default_factory=list)
    pool: PoolResponse | None = None
    route_chain: RouteChainResponse | None = None
    story_plan: StoryPlan | None = None
    validation: ValidationResult | None = None
    critique: Critique | None = None
    steps: list[ToolCall] = Field(default_factory=list)


@router.post("/run", response_model=AgentRunResponse)
def run_agent(request: AgentRunRequest) -> AgentRunResponse:
    state = build_initial_state(request)
    final = Conductor(get_tool_registry(), LlmClient()).run(state)
    save_state(final)
    return _response_from_state(final)


@router.post("/adjust", response_model=AgentRunResponse)
def adjust_agent(request: AgentAdjustRequest) -> AgentRunResponse:
    parent = load_state(request.parent_session_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="Parent agent session not found")
    state = build_adjust_state(parent, request)
    final = Conductor(get_tool_registry(), LlmClient()).run(state)
    save_state(final)
    return _response_from_state(final)


@router.get("/trace/{session_id}", response_model=AgentRunResponse)
def get_trace(session_id: str) -> AgentRunResponse:
    state = load_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Agent session not found")
    return _response_from_state(state)


@router.get("/stream/{session_id}")
def stream_trace(session_id: str) -> StreamingResponse:
    if load_state(session_id) is None:
        raise HTTPException(status_code=404, detail="Agent session not found")
    return StreamingResponse(
        iter([format_sse(get_trace_events(session_id))]),
        media_type="text/event-stream",
    )


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


def build_adjust_state(parent: AgentState, request: AgentAdjustRequest) -> AgentState:
    state = parent.model_copy(deep=True)
    state.goal = AgentGoal(
        kind="adjust_route",
        raw_query=request.user_message,
        session_id=request.session_id or uuid4().hex,
        user_id=parent.goal.user_id,
        locale_city=parent.goal.locale_city,
    )
    state.steps = []
    state.phase = "UNDERSTANDING"
    state.trace_id = uuid4().hex
    state.memory.route_chain = None
    state.memory.validation = None
    state.memory.critique = None
    state.memory.feedback_intent = None
    state.memory.feedback_applied = False
    return state


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
        story_plan=state.memory.story_plan,
        validation=state.memory.validation,
        critique=state.memory.critique,
        steps=state.steps,
    )

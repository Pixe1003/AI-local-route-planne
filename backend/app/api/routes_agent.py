import asyncio
import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.conductor import Conductor
from app.agent.state import AgentGoal, AgentState, Critique, ToolCall
from app.agent.story_models import StoryPlan
from app.agent.session_summarizer import summarize_session
from app.agent.store import list_sessions, load_state, save_state, session_cost_summary
from app.agent.tools import get_tool_registry
from app.agent.tracing import get_trace_events, subscribe, unsubscribe
from app.agent.user_memory import get_user_facts
from app.config import get_settings
from app.llm.client import LlmClient
from app.observability.metrics import MEMORY_LAYER_USAGE
from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import PlanContext, ValidationResult
from app.schemas.pool import PoolResponse, TimeWindow
from app.schemas.preferences import PreferenceSnapshot
from app.schemas.route import RouteChainResponse
from app.schemas.user_memory import SimilarSessionHit, UserFacts


router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRunRequest(BaseModel):
    user_id: str
    free_text: str
    city: str = "hefei"
    time_window: TimeWindow | None = None
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
async def run_agent(request: AgentRunRequest) -> AgentRunResponse:
    state = build_initial_state(request)
    loop = asyncio.get_running_loop()
    final = await loop.run_in_executor(
        None,
        lambda: Conductor(get_tool_registry(), LlmClient()).run(state),
    )
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


@router.get("/tools")
def list_agent_tools() -> list[dict]:
    return get_tool_registry().schemas_for_llm()


@router.get("/cost/{session_id}")
def get_session_cost(session_id: str) -> dict:
    summary = session_cost_summary(session_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Session not found")
    return summary


@router.get("/user/{user_id}/facts", response_model=UserFacts)
def get_user_facts_endpoint(user_id: str, force_refresh: bool = False) -> UserFacts:
    return get_user_facts(user_id, force_refresh=force_refresh)


@router.get("/stream/{session_id}")
async def stream_trace(session_id: str) -> StreamingResponse:
    async def gen():
        queue = subscribe(session_id)
        try:
            for event in get_trace_events(session_id):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") in {"finished", "failed"}:
                    return
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") in {"finished", "failed"}:
                    break
        finally:
            unsubscribe(session_id, queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def build_initial_state(request: AgentRunRequest) -> AgentState:
    session_id = request.session_id or uuid4().hex
    time_window = request.time_window or TimeWindow(start="13:00", end="21:00")
    context = PlanContext(
        city=request.city,
        date=request.date,
        time_window=time_window,
        party="friends",
        budget_per_person=request.budget_per_person,
    )
    profile = UserNeedProfile.from_plan_context(context, raw_query=request.free_text)
    profile.user_id = request.user_id
    state = AgentState(
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
    _enrich_initial_memory(state, request, session_id)
    return state


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


def _enrich_initial_memory(
    state: AgentState,
    request: AgentRunRequest,
    session_id: str,
) -> None:
    state.memory.episodic_summary = _load_episodic_summaries(request.user_id)
    if state.memory.episodic_summary:
        MEMORY_LAYER_USAGE.labels(layer="episodic").inc()
    try:
        facts = get_user_facts(request.user_id)
    except Exception:
        facts = None
    state.memory.user_facts = facts
    if facts and facts.session_count > 0:
        MEMORY_LAYER_USAGE.labels(layer="semantic").inc()
    if facts and facts.rejected_poi_ids:
        state.profile.must_avoid = list(
            dict.fromkeys([*state.profile.must_avoid, *facts.rejected_poi_ids])
        )
    if request.time_window is None and facts and facts.typical_time_windows:
        from app.agent.user_memory import bucket_to_time_window

        inferred = bucket_to_time_window(facts.typical_time_windows[0])
        if inferred:
            state.context.time_window = TimeWindow(start=inferred[0], end=inferred[1])
            state.profile.time.start_time = inferred[0]
            state.profile.time.end_time = inferred[1]
    if not get_settings().prefer_tool_recall_in_trace:
        try:
            state.memory.similar_sessions = _load_similar_sessions(request, session_id)
        except Exception:
            state.memory.similar_sessions = []
        else:
            state.memory.similar_sessions_searched = True
            if state.memory.similar_sessions:
                MEMORY_LAYER_USAGE.labels(layer="vector").inc()


def _load_episodic_summaries(user_id: str) -> list:
    summaries = []
    for past_state in list_sessions(user_id, limit=5):
        if past_state.memory.story_plan is None:
            continue
        try:
            summaries.append(summarize_session(past_state))
        except Exception:
            continue
    return summaries


def _load_similar_sessions(
    request: AgentRunRequest,
    session_id: str,
) -> list[SimilarSessionHit]:
    from app.repositories.session_vector_repo import get_session_vector_repo

    return get_session_vector_repo().search_similar(
        request.user_id,
        request.free_text,
        top_k=3,
        exclude_session_id=session_id,
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
        story_plan=state.memory.story_plan,
        validation=state.memory.validation,
        critique=state.memory.critique,
        steps=state.steps,
    )

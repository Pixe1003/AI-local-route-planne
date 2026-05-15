from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.agent.state import AgentState, ToolCall
from app.agent.tracing import record_event, reset_trace
from app.agent.tools import ToolRegistry, ToolResult
from app.config import get_settings
from app.llm.client import LlmClient
from app.observability.logging import get_logger
from app.observability.metrics import AGENT_RUN_LATENCY, TOOL_LATENCY
from app.observability.tracing import tracer


logger = get_logger(__name__)


class Decision(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    tokens_used: int = 0


class Conductor:
    MAX_STEPS = 12

    def __init__(self, tools: ToolRegistry, llm: LlmClient) -> None:
        self.tools = tools
        self.llm = llm

    def run(self, state: AgentState) -> AgentState:
        reset_trace(state.goal.session_id)
        run_started = datetime.now(timezone.utc)
        bind_contextvars(
            session_id=state.goal.session_id,
            trace_id=state.trace_id,
            user_id=state.goal.user_id,
            goal_kind=state.goal.kind,
        )
        logger.info("agent.run.started", phase=state.phase)
        try:
            for _ in range(self.MAX_STEPS):
                decision = self._decide(state)
                logger.info("agent.tool.decided", tool=decision.tool, phase=state.phase)
                record_event(
                    state.goal.session_id,
                    {"type": "decided", "tool": decision.tool, "phase": state.phase, "args": decision.args},
                )
                if decision.tool == "finish":
                    state.phase = "DONE"
                    record_event(state.goal.session_id, {"type": "finished", "phase": state.phase})
                    logger.info("agent.run.finished", phase=state.phase)
                    return state
                started = datetime.now(timezone.utc)
                call = ToolCall(
                    tool_name=decision.tool,
                    args=decision.args,
                    started_at=started,
                    tokens_used=decision.tokens_used,
                )
                try:
                    with tracer.start_as_current_span(f"tool.{decision.tool}") as span:
                        span.set_attribute("tool.name", decision.tool)
                        span.set_attribute("session.id", state.goal.session_id)
                        span.set_attribute("trace.id", state.trace_id)
                        span.set_attribute("user.id", state.goal.user_id)
                        span.set_attribute("goal.kind", state.goal.kind)
                        result = self.tools.execute(decision.tool, state, decision.args)
                    ended = datetime.now(timezone.utc)
                    call.ended_at = ended
                    call.latency_ms = int((ended - started).total_seconds() * 1000)
                    call.observation_summary = result.observation_summary
                    call.observation_payload_ref = result.observation_payload_ref
                    state.steps.append(call)
                    self._apply_result(state, result)
                    TOOL_LATENCY.labels(tool_name=decision.tool, status="ok").observe(
                        (ended - started).total_seconds()
                    )
                    record_event(
                        state.goal.session_id,
                        {
                            "type": "observed",
                            "tool": decision.tool,
                            "phase": state.phase,
                            "observation_summary": result.observation_summary,
                            "observation_payload_ref": result.observation_payload_ref,
                            "latency_ms": call.latency_ms,
                        },
                    )
                except Exception as exc:
                    ended = datetime.now(timezone.utc)
                    call.ended_at = ended
                    call.latency_ms = int((ended - started).total_seconds() * 1000)
                    call.error = str(exc)
                    state.steps.append(call)
                    state.phase = "FAILED"
                    TOOL_LATENCY.labels(tool_name=decision.tool, status="error").observe(
                        (ended - started).total_seconds()
                    )
                    logger.error("agent.tool.failed", tool=decision.tool, phase=state.phase, exc_info=True)
                    record_event(
                        state.goal.session_id,
                        {"type": "failed", "tool": decision.tool, "error": str(exc), "phase": state.phase},
                    )
                    raise
            state.phase = "FAILED"
            record_event(state.goal.session_id, {"type": "failed", "phase": state.phase, "error": "max_steps"})
            logger.error("agent.run.failed", phase=state.phase, error="max_steps")
            return state
        finally:
            run_ended = datetime.now(timezone.utc)
            AGENT_RUN_LATENCY.labels(goal_kind=state.goal.kind, phase=state.phase).observe(
                (run_ended - run_started).total_seconds()
            )
            clear_contextvars()

    def _decide(self, state: AgentState) -> Decision:
        fallback = self._rule_based_decision(state)
        settings = get_settings()
        if not settings.agent_tool_calling_enabled:
            return fallback
        if getattr(settings, "agent_fast_decision_enabled", False):
            return fallback
        raw = self.llm.complete_tool_call(
            self._build_decision_prompt(state),
            tools=self.tools.schemas_for_llm(),
            fallback=fallback.model_dump(),
        )
        tokens_used = int(raw.pop("_tokens_used", 0) or 0)
        decision = Decision.model_validate(raw)
        decision.tokens_used = tokens_used
        valid_tools = {schema["name"] for schema in self.tools.schemas_for_llm()}
        if decision.tool in valid_tools or decision.tool == "finish":
            return decision
        return fallback

    def _rule_based_decision(self, state: AgentState) -> Decision:
        if state.goal.kind == "adjust_route":
            if state.memory.feedback_intent is None:
                return Decision(tool="parse_feedback", args={"message": state.goal.raw_query})
            if not state.memory.feedback_applied:
                return Decision(tool="replan_by_event", args={})
            if state.memory.route_chain is None:
                return Decision(
                    tool="get_amap_chain",
                    args={
                        "poi_ids": [stop.poi_id for stop in state.memory.story_plan.stops]
                        if state.memory.story_plan
                        else [],
                        "mode": "driving",
                    },
                )
            if state.memory.validation is None:
                return Decision(tool="validate_route", args={})
            if state.memory.critique is None:
                return Decision(tool="critique", args={})
            return Decision(tool="finish", args={})

        if state.memory.intent is None:
            return Decision(tool="parse_intent", args={"free_text": state.goal.raw_query})
        if state.memory.episodic_summary and not state.memory.similar_sessions_searched:
            return Decision(
                tool="recall_similar_sessions",
                args={"query": state.goal.raw_query, "top_k": 3},
            )
        if not state.memory.ugc_searched:
            return Decision(
                tool="search_ugc_evidence",
                args={"query": state.goal.raw_query, "city": state.context.city, "top_k": 8},
            )
        if state.memory.pool is None:
            return Decision(
                tool="recommend_pool",
                args={"free_text": state.goal.raw_query, "city": state.context.city},
            )
        if state.memory.story_plan is None:
            return Decision(tool="compose_story", args={"max_stops": 5})
        if state.memory.route_chain is None:
            return Decision(
                tool="get_amap_chain",
                args={
                    "poi_ids": [stop.poi_id for stop in state.memory.story_plan.stops],
                    "mode": "driving",
                },
            )
        if state.memory.validation is None:
            return Decision(tool="validate_route", args={})
        if state.memory.critique is None:
            return Decision(tool="critique", args={})
        return Decision(tool="finish", args={})

    def _build_decision_prompt(self, state: AgentState) -> str:
        completed = [step.tool_name for step in state.steps]
        facts_block = ""
        if state.memory.user_facts and state.memory.user_facts.session_count > 0:
            facts_block = f"; user_facts={state.memory.user_facts.to_prompt_block()}"
        return (
            "Choose the next AIroute agent tool. "
            f"phase={state.phase}; completed={completed}; "
            f"has_intent={state.memory.intent is not None}; "
            f"has_pool={state.memory.pool is not None}; "
            f"has_story={state.memory.story_plan is not None}; "
            f"has_route={state.memory.route_chain is not None}; "
            f"has_validation={state.memory.validation is not None}; "
            f"has_critique={state.memory.critique is not None}"
            f"{facts_block}"
        )

    def _apply_result(self, state: AgentState, result: ToolResult) -> None:
        for key, value in result.memory_patch.items():
            setattr(state.memory, key, value)
        if result.next_phase:
            state.phase = result.next_phase

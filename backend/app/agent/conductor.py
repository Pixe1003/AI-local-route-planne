from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.agent.state import AgentState, ToolCall
from app.agent.tools import ToolRegistry, ToolResult
from app.config import get_settings
from app.llm.client import LlmClient


class Decision(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


class Conductor:
    MAX_STEPS = 8

    def __init__(self, tools: ToolRegistry, llm: LlmClient) -> None:
        self.tools = tools
        self.llm = llm

    def run(self, state: AgentState) -> AgentState:
        for _ in range(self.MAX_STEPS):
            decision = self._decide(state)
            if decision.tool == "finish":
                state.phase = "DONE"
                return state
            started = datetime.now(timezone.utc)
            call = ToolCall(tool_name=decision.tool, args=decision.args, started_at=started)
            try:
                result = self.tools.execute(decision.tool, state, decision.args)
                ended = datetime.now(timezone.utc)
                call.ended_at = ended
                call.latency_ms = int((ended - started).total_seconds() * 1000)
                call.observation_summary = result.observation_summary
                state.steps.append(call)
                self._apply_result(state, result)
            except Exception as exc:
                ended = datetime.now(timezone.utc)
                call.ended_at = ended
                call.latency_ms = int((ended - started).total_seconds() * 1000)
                call.error = str(exc)
                state.steps.append(call)
                state.phase = "FAILED"
                raise
        state.phase = "FAILED"
        return state

    def _decide(self, state: AgentState) -> Decision:
        fallback = self._rule_based_decision(state)
        if not get_settings().agent_tool_calling_enabled:
            return fallback
        raw = self.llm.complete_tool_call(
            self._build_decision_prompt(state),
            tools=self.tools.schemas_for_llm(),
            fallback=fallback.model_dump(),
        )
        decision = Decision.model_validate(raw)
        if decision.tool != fallback.tool:
            return fallback
        return fallback

    def _rule_based_decision(self, state: AgentState) -> Decision:
        if state.memory.intent is None:
            return Decision(tool="parse_intent", args={"free_text": state.goal.raw_query})
        if state.memory.pool is None:
            return Decision(
                tool="recommend_pool",
                args={"free_text": state.goal.raw_query, "city": state.context.city},
            )
        if state.memory.route_chain is None:
            return Decision(
                tool="get_amap_chain",
                args={"poi_ids": state.memory.pool.default_selected_ids[:5], "mode": "driving"},
            )
        return Decision(tool="finish", args={})

    def _build_decision_prompt(self, state: AgentState) -> str:
        completed = [step.tool_name for step in state.steps]
        return (
            "Choose the next AIroute agent tool. "
            f"phase={state.phase}; completed={completed}; "
            f"has_intent={state.memory.intent is not None}; "
            f"has_pool={state.memory.pool is not None}; "
            f"has_route={state.memory.route_chain is not None}"
        )

    def _apply_result(self, state: AgentState, result: ToolResult) -> None:
        for key, value in result.memory_patch.items():
            setattr(state.memory, key, value)
        if result.next_phase:
            state.phase = result.next_phase

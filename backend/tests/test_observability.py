from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from app.agent.state import AgentGoal, AgentState, ToolCall
from app.agent.store import save_state
from app.agent.tools import ToolResult
from app.api import routes_route
from app.main import app
from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import PlanContext
from app.schemas.pool import TimeWindow
from app.services.amap.schemas import AmapRouteMode, AmapRouteResult, AmapRouteStep


client = TestClient(app)


def _patch_route_client(monkeypatch) -> None:
    class FakeRouteClient:
        def get_route(self, **kwargs: Any) -> AmapRouteResult:
            return AmapRouteResult(
                mode=AmapRouteMode.DRIVING,
                distance_m=900,
                duration_s=480,
                steps=[
                    AmapRouteStep(
                        instruction="drive",
                        road_name="demo road",
                        distance_m=900,
                        duration_s=480,
                        polyline_coordinates=[[117.23, 31.82], [117.24, 31.83]],
                    )
                ],
                polyline_coordinates=[],
                raw_response={"status": "1"},
            )

        def close(self) -> None:
            return None

    monkeypatch.setattr(routes_route, "AmapRouteClient", FakeRouteClient, raising=False)


def test_metrics_endpoint_exposes_agent_tool_latency_after_run(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    _patch_route_client(monkeypatch)

    response = client.post(
        "/api/agent/run",
        json={
            "user_id": "metrics_user",
            "free_text": "local food route",
            "city": "hefei",
            "date": "2026-05-08",
            "time_window": {"start": "14:00", "end": "20:00"},
            "budget_per_person": 180,
        },
    )
    assert response.status_code == 200

    metrics = client.get("/metrics")

    assert metrics.status_code == 200
    assert 'agent_tool_latency_seconds_count{status="ok",tool_name="parse_intent"}' in metrics.text
    assert "agent_run_latency_seconds_count" in metrics.text


def test_session_cost_endpoint_summarizes_persisted_step_tokens_and_latency(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.agent.store.DB_PATH", tmp_path / "agent_sessions.sqlite", raising=False)
    monkeypatch.setattr("app.agent.store._persist_session_vector", lambda state: None, raising=False)

    context = PlanContext(
        city="hefei",
        date="2026-05-08",
        time_window=TimeWindow(start="14:00", end="20:00"),
        party="friends",
        budget_per_person=180,
    )
    state = AgentState(
        goal=AgentGoal(raw_query="local food", session_id="cost_session", user_id="cost_user"),
        profile=UserNeedProfile.from_plan_context(context, raw_query="local food"),
        context=context,
        phase="DONE",
        steps=[
            ToolCall(
                tool_name="parse_intent",
                started_at=datetime.now(timezone.utc),
                latency_ms=25,
                tokens_used=11,
            ),
            ToolCall(
                tool_name="compose_story",
                started_at=datetime.now(timezone.utc),
                latency_ms=125,
                tokens_used=30,
            ),
        ],
    )
    save_state(state)

    response = client.get("/api/agent/cost/cost_session")

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "cost_session",
        "total_tokens": 41,
        "total_latency_ms": 150,
        "tool_count": 2,
        "tools_by_latency": [
            {"name": "compose_story", "ms": 125},
            {"name": "parse_intent", "ms": 25},
        ],
        "estimated_cost_usd": 0.000008,
    }


def test_session_cost_endpoint_returns_404_for_unknown_session(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.agent.store.DB_PATH", tmp_path / "agent_sessions.sqlite", raising=False)

    response = client.get("/api/agent/cost/missing_session")

    assert response.status_code == 404


def test_llm_tool_call_returns_total_tokens(monkeypatch) -> None:
    def fake_settings():
        return SimpleNamespace(
            llm_api_key="test-key",
            llm_base_url="https://api.example.com/v1",
            llm_auth_header="authorization",
            llm_model="test-model",
            llm_timeout_seconds=12,
        )

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "parse_intent",
                                        "arguments": '{"free_text":"local food"}',
                                    }
                                }
                            ]
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }

    monkeypatch.setattr("app.llm.client.get_settings", fake_settings)
    monkeypatch.setattr("app.llm.client.httpx.post", lambda *args, **kwargs: FakeResponse())

    from app.llm.client import LlmClient

    result = LlmClient().complete_tool_call(
        "choose",
        tools=[{"name": "parse_intent", "parameters": {"type": "object"}}],
        fallback={"tool": "finish", "args": {}},
    )

    assert result == {"tool": "parse_intent", "args": {"free_text": "local food"}, "_tokens_used": 15}


def test_conductor_records_llm_decision_tokens_on_tool_call(monkeypatch) -> None:
    from app.agent.conductor import Conductor

    monkeypatch.setattr(
        "app.agent.conductor.get_settings",
        lambda: SimpleNamespace(agent_tool_calling_enabled=True, agent_fast_decision_enabled=False),
    )

    class FakeTools:
        def schemas_for_llm(self):
            return [{"name": "parse_intent", "parameters": {"type": "object"}}]

        def execute(self, tool_name: str, state: AgentState, args: dict[str, Any]) -> ToolResult:
            return ToolResult(observation_summary="parsed", memory_patch={"intent": {"ok": True}})

    class FakeLlm:
        def __init__(self) -> None:
            self.calls = 0

        def complete_tool_call(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            self.calls += 1
            if self.calls == 1:
                return {
                    "tool": "parse_intent",
                    "args": {"free_text": "local food"},
                    "_tokens_used": 17,
                }
            return {"tool": "finish", "args": {}, "_tokens_used": 3}

    context = PlanContext(
        city="hefei",
        date="2026-05-08",
        time_window=TimeWindow(start="14:00", end="20:00"),
        party="friends",
        budget_per_person=180,
    )
    state = AgentState(
        goal=AgentGoal(raw_query="local food", session_id="token_session", user_id="token_user"),
        profile=UserNeedProfile.from_plan_context(context, raw_query="local food"),
        context=context,
    )

    final = Conductor(FakeTools(), FakeLlm()).run(state)

    assert final.phase == "DONE"
    assert final.steps[0].tool_name == "parse_intent"
    assert final.steps[0].tokens_used == 17


def test_configure_otel_sets_provider_only_when_endpoint_is_configured(monkeypatch) -> None:
    from app.observability.tracing import configure_otel

    providers: list[object] = []
    monkeypatch.setattr(
        "app.observability.tracing.trace.set_tracer_provider",
        lambda provider: providers.append(provider),
    )

    configure_otel(service_name="airoute-test", endpoint=None)
    assert providers == []

    configure_otel(service_name="airoute-test", endpoint="http://collector:4317")

    assert len(providers) == 1


def test_conductor_wraps_tool_execution_in_trace_span(monkeypatch) -> None:
    from app.agent.conductor import Conductor

    monkeypatch.setattr(
        "app.agent.conductor.get_settings",
        lambda: SimpleNamespace(agent_tool_calling_enabled=False, agent_fast_decision_enabled=True),
    )

    class FakeSpan:
        def __init__(self, name: str) -> None:
            self.name = name
            self.attributes: dict[str, object] = {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def set_attribute(self, key: str, value: object) -> None:
            self.attributes[key] = value

    class FakeTracer:
        def __init__(self) -> None:
            self.spans: list[FakeSpan] = []

        def start_as_current_span(self, name: str) -> FakeSpan:
            span = FakeSpan(name)
            self.spans.append(span)
            return span

    class FakeTools:
        def schemas_for_llm(self):
            return [{"name": "parse_intent", "parameters": {"type": "object"}}]

        def execute(self, tool_name: str, state: AgentState, args: dict[str, Any]) -> ToolResult:
            return ToolResult(observation_summary="parsed", memory_patch={"intent": {"ok": True}})

    context = PlanContext(
        city="hefei",
        date="2026-05-08",
        time_window=TimeWindow(start="14:00", end="20:00"),
        party="friends",
        budget_per_person=180,
    )
    state = AgentState(
        goal=AgentGoal(raw_query="local food", session_id="span_session", user_id="span_user"),
        profile=UserNeedProfile.from_plan_context(context, raw_query="local food"),
        context=context,
    )
    fake_tracer = FakeTracer()
    monkeypatch.setattr("app.agent.conductor.tracer", fake_tracer)

    Conductor(FakeTools(), llm=object()).run(state)

    assert fake_tracer.spans
    span = fake_tracer.spans[0]
    assert span.name == "tool.parse_intent"
    assert span.attributes["tool.name"] == "parse_intent"
    assert span.attributes["session.id"] == "span_session"
    assert span.attributes["user.id"] == "span_user"

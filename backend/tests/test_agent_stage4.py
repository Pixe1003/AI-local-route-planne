from typing import Any

from fastapi.testclient import TestClient

from app.agent.specialists.repair_agent import RepairAgent
from app.config import get_settings
from app.agent.store import load_state
from app.api import routes_route
from app.main import app
from app.services.amap.schemas import AmapRouteMode, AmapRouteResult, AmapRouteStep


client = TestClient(app)


def _patch_route_client(monkeypatch) -> None:
    class FakeRouteClient:
        def get_route(self, **kwargs: Any) -> AmapRouteResult:
            return AmapRouteResult(
                mode=AmapRouteMode.DRIVING,
                distance_m=800,
                duration_s=420,
                steps=[
                    AmapRouteStep(
                        instruction="drive",
                        road_name="demo road",
                        distance_m=800,
                        duration_s=420,
                        polyline_coordinates=[[121.49, 31.24], [121.48, 31.23]],
                    )
                ],
                polyline_coordinates=[],
                raw_response={"status": "1"},
            )

        def close(self) -> None:
            return None

    monkeypatch.setattr(routes_route, "AmapRouteClient", FakeRouteClient, raising=False)


def test_repair_agent_parses_composite_feedback_without_llm() -> None:
    intent = RepairAgent().parse("第二站换近的火锅，预算到250")

    assert intent.event_type == "REPLACE_POI"
    assert intent.target_stop_index == 1
    assert intent.category_hint == "hotpot"
    assert intent.budget_per_person == 250
    assert "budget_per_person" in intent.deltas
    assert "category_hint" in intent.deltas


def test_repair_agent_merges_llm_feedback_slots(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "fake-key")
    monkeypatch.setenv("AGENT_TOOL_CALLING_ENABLED", "true")
    get_settings.cache_clear()

    class FakeLlmClient:
        def complete_json(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            return {
                "event_type": "USER_MODIFY_CONSTRAINT",
                "target_stop_index": None,
                "category_hint": "cafe",
                "budget_per_person": None,
                "deltas": {"meal_slot": "lunch", "budget_direction": "lower"},
            }

    monkeypatch.setattr(
        "app.agent.specialists.repair_agent.LlmClient",
        lambda: FakeLlmClient(),
    )

    intent = RepairAgent().parse("把午餐那站改成更便宜的咖啡店")

    assert intent.event_type == "USER_MODIFY_CONSTRAINT"
    assert intent.category_hint == "cafe"
    assert intent.budget_per_person is None
    assert intent.deltas["meal_slot"] == "lunch"
    assert intent.deltas["budget_direction"] == "lower"


def test_agent_tools_endpoint_exposes_feedback_tools() -> None:
    response = client.get("/api/agent/tools")

    assert response.status_code == 200
    names = {tool["name"] for tool in response.json()}
    assert {"parse_feedback", "replan_by_event"} <= names


def test_agent_adjust_reuses_parent_state_and_records_feedback_trace(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    _patch_route_client(monkeypatch)
    initial = client.post(
        "/api/agent/run",
        json={
            "user_id": "mock_user",
            "free_text": "quiet local food and photos",
            "city": "shanghai",
            "date": "2026-05-08",
            "time_window": {"start": "14:00", "end": "20:00"},
            "budget_per_person": 180,
        },
    ).json()

    response = client.post(
        "/api/agent/adjust",
        json={
            "parent_session_id": initial["session_id"],
            "user_message": "第二站换近的火锅，预算到250",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["phase"] == "DONE"
    assert data["session_id"] != initial["session_id"]
    assert data["ordered_poi_ids"]
    assert [step["tool_name"] for step in data["steps"]] == [
        "parse_feedback",
        "replan_by_event",
        "get_amap_chain",
        "validate_route",
        "critique",
    ]
    adjusted_state = load_state(data["session_id"])
    assert adjusted_state is not None
    assert adjusted_state.context.budget_per_person == 250
    assert adjusted_state.memory.feedback_intent["category_hint"] == "hotpot"


def test_agent_stream_returns_recorded_sse_events(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    _patch_route_client(monkeypatch)
    run = client.post(
        "/api/agent/run",
        json={
            "user_id": "mock_user",
            "free_text": "quiet local food and photos",
            "city": "shanghai",
            "date": "2026-05-08",
            "time_window": {"start": "14:00", "end": "20:00"},
            "budget_per_person": 180,
        },
    ).json()

    response = client.get(f"/api/agent/stream/{run['session_id']}")

    assert response.status_code == 200
    body = response.text
    assert "data:" in body
    assert "parse_intent" in body
    assert "critique" in body

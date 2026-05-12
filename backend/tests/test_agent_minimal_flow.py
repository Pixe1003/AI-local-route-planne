from typing import Any

from fastapi.testclient import TestClient

from app.api import routes_route
from app.agent import conductor
from app.llm.client import LlmClient
from app.services import intent_service
from app.main import app
from app.services.amap.schemas import AmapRouteMode, AmapRouteResult, AmapRouteStep


client = TestClient(app)


def make_route_result(
    *,
    mode: AmapRouteMode = AmapRouteMode.DRIVING,
    distance_m: float,
    duration_s: float,
) -> AmapRouteResult:
    return AmapRouteResult(
        mode=mode,
        distance_m=distance_m,
        duration_s=duration_s,
        steps=[
            AmapRouteStep(
                instruction="drive to next POI",
                road_name="demo road",
                distance_m=distance_m,
                duration_s=duration_s,
                polyline_coordinates=[
                    [117.2272, 31.8206],
                    [117.235, 31.826],
                ],
            )
        ],
        polyline_coordinates=[],
        raw_response={"status": "1"},
    )


def patch_route_client(monkeypatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    class FakeRouteClient:
        def get_route(self, **kwargs: Any) -> AmapRouteResult:
            calls.append(kwargs)
            return make_route_result(distance_m=1200 + len(calls), duration_s=600)

        def close(self) -> None:
            return None

    monkeypatch.setattr(routes_route, "AmapRouteClient", FakeRouteClient, raising=False)
    return calls


def test_llm_complete_tool_call_uses_fallback_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    fallback = {"tool": "parse_intent", "args": {"free_text": "少排队"}}

    decision = LlmClient().complete_tool_call("choose next tool", tools=[], fallback=fallback)

    assert decision == fallback


def test_agent_run_fallback_executes_minimal_tool_chain(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    route_calls = patch_route_client(monkeypatch)

    response = client.post(
        "/api/agent/run",
        json={
            "user_id": "mock_user",
            "free_text": "今天下午想少排队、吃本地菜、顺路拍照",
            "city": "hefei",
            "date": "2026-05-08",
            "time_window": {"start": "14:00", "end": "20:00"},
            "budget_per_person": 180,
            "preference_snapshot": {
                "user_id": "mock_user",
                "city": "hefei",
                "liked_poi_ids": [],
                "disliked_poi_ids": [],
                "tag_weights": {},
                "category_weights": {},
                "keyword_weights": {},
                "source": "test",
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["phase"] == "DONE"
    assert data["session_id"]
    assert data["trace_id"]
    assert len(data["ordered_poi_ids"]) >= 2
    assert data["route_chain"]["ordered_pois"]
    assert len(route_calls) == len(data["ordered_poi_ids"]) - 1
    assert [step["tool_name"] for step in data["steps"]] == [
        "parse_intent",
        "recommend_pool",
        "get_amap_chain",
    ]


def test_agent_run_uses_rule_sequence_without_llm_decision_by_default(monkeypatch) -> None:
    def fail_if_llm_decision_is_used(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("LLM tool calling should be opt-in for the stage 1 fallback flow")

    monkeypatch.setattr(conductor.LlmClient, "complete_tool_call", fail_if_llm_decision_is_used)
    monkeypatch.setattr(intent_service.LlmClient, "complete_json", fail_if_llm_decision_is_used)
    patch_route_client(monkeypatch)

    response = client.post(
        "/api/agent/run",
        json={
            "user_id": "mock_user",
            "free_text": "今天下午想少排队、吃本地菜、顺路拍照",
            "city": "hefei",
            "date": "2026-05-08",
            "time_window": {"start": "14:00", "end": "20:00"},
            "budget_per_person": 180,
        },
    )

    assert response.status_code == 200
    assert response.json()["phase"] == "DONE"

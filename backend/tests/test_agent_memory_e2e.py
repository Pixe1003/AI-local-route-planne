from typing import Any

from fastapi.testclient import TestClient

from app.api import routes_route
from app.main import app
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
                        polyline_coordinates=[[117.22, 31.82], [117.23, 31.83]],
                    )
                ],
                polyline_coordinates=[],
                raw_response={"status": "1"},
            )

        def close(self) -> None:
            return None

    monkeypatch.setattr(routes_route, "AmapRouteClient", FakeRouteClient, raising=False)


def test_three_layer_memory_flow_skips_rejected_poi_and_exposes_facts(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.agent.store.DB_PATH", tmp_path / "agent_sessions.sqlite", raising=False)
    monkeypatch.setattr("app.agent.store._persist_session_vector", lambda state: None, raising=False)
    monkeypatch.setattr(
        "app.api.routes_agent._load_similar_sessions",
        lambda request, session_id: [],
        raising=False,
    )
    _patch_route_client(monkeypatch)

    first = client.post(
        "/api/agent/run",
        json={
            "user_id": "memory_e2e",
            "free_text": "想吃火锅和本地菜",
            "city": "hefei",
            "date": "2026-05-08",
            "time_window": {"start": "12:00", "end": "20:00"},
            "budget_per_person": 180,
        },
    ).json()
    rejected_poi_id = first["story_plan"]["stops"][0]["poi_id"]

    adjusted = client.post(
        "/api/agent/adjust",
        json={
            "parent_session_id": first["session_id"],
            "user_message": "换掉第一站，预算到220",
        },
    )
    assert adjusted.status_code == 200

    third = client.post(
        "/api/agent/run",
        json={
            "user_id": "memory_e2e",
            "free_text": "再来一次火锅和本地菜",
            "city": "hefei",
            "date": "2026-05-09",
            "time_window": {"start": "12:00", "end": "20:00"},
            "budget_per_person": 180,
        },
    ).json()

    third_stop_ids = [stop["poi_id"] for stop in third["story_plan"]["stops"]]
    assert rejected_poi_id not in third_stop_ids

    facts = client.get("/api/agent/user/memory_e2e/facts?force_refresh=true").json()
    assert facts["session_count"] >= 2
    assert rejected_poi_id in facts["rejected_poi_ids"]

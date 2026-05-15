from typing import Any

from fastapi.testclient import TestClient

from app.api import routes_route
from app.main import app
from app.services.amap.schemas import AmapRouteMode, AmapRouteResult, AmapRouteStep


client = TestClient(app)


def test_agent_run_response_shape(snapshot, monkeypatch) -> None:
    _patch_route_client(monkeypatch)

    response = client.post(
        "/api/agent/run",
        json={
            "user_id": "snapshot_user",
            "free_text": "fixed query for snapshot",
            "city": "hefei",
            "date": "2026-05-08",
            "time_window": {"start": "12:00", "end": "20:00"},
            "budget_per_person": 180,
        },
    )

    assert response.status_code == 200
    assert _extract_shape(response.json()) == snapshot


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


def _extract_shape(obj):
    if isinstance(obj, dict):
        return {key: _extract_shape(value) for key, value in sorted(obj.items())}
    if isinstance(obj, list):
        if not obj:
            return []
        return [_extract_shape(obj[0])]
    return type(obj).__name__

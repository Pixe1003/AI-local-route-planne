from typing import Any

from fastapi.testclient import TestClient
import pytest

from app.api import route as route_api
from app.main import app
from app.services.amap.errors import AmapConfigError, AmapUpstreamError
from app.services.amap.schemas import (
    AmapRouteMode,
    AmapRouteResult,
    AmapRouteStep,
)


client = TestClient(app)


def route_payload(poi_count: int = 3, mode: str = "walking") -> dict[str, Any]:
    pois = [
        {
            "id": "poi_001",
            "name": "Lake",
            "longitude": 118.8012,
            "latitude": 32.0735,
        },
        {
            "id": "poi_002",
            "name": "Museum",
            "longitude": 118.7921,
            "latitude": 32.0443,
        },
        {
            "id": "poi_003",
            "name": "Temple",
            "longitude": 118.7889,
            "latitude": 32.0206,
        },
    ]
    return {"mode": mode, "pois": pois[:poi_count]}


def route_result(
    *,
    mode: AmapRouteMode,
    distance_m: float,
    duration_s: float | None,
    step_prefix: str,
) -> AmapRouteResult:
    return AmapRouteResult(
        mode=mode,
        distance_m=distance_m,
        duration_s=duration_s,
        steps=[
            AmapRouteStep(
                instruction=f"{step_prefix} step 1",
                road_name=f"{step_prefix} road 1",
                distance_m=distance_m / 2,
                duration_s=None if duration_s is None else duration_s / 2,
                polyline_coordinates=[
                    [118.8012, 32.0735],
                    [118.802, 32.074],
                ],
            ),
            AmapRouteStep(
                instruction=f"{step_prefix} step 2",
                road_name=f"{step_prefix} road 2",
                distance_m=distance_m / 2,
                duration_s=None if duration_s is None else duration_s / 2,
                polyline_coordinates=[
                    [118.802, 32.074],
                    [118.803, 32.075],
                ],
            ),
        ],
        polyline_coordinates=[
            [118.8012, 32.0735],
            [118.802, 32.074],
            [118.803, 32.075],
        ],
        raw_response={"status": "1"},
    )


def patch_route_client(
    monkeypatch: pytest.MonkeyPatch,
    results: list[AmapRouteResult],
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    class FakeRouteClient:
        async def get_route(self, **kwargs: Any) -> AmapRouteResult:
            calls.append(kwargs)
            return results[len(calls) - 1]

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(route_api, "AmapRouteClient", FakeRouteClient)
    return calls


def test_two_pois_generate_one_segment(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = patch_route_client(
        monkeypatch,
        [
            route_result(
                mode=AmapRouteMode.WALKING,
                distance_m=2000,
                duration_s=1300,
                step_prefix="segment 1",
            )
        ],
    )

    response = client.post("/api/route/chain", json=route_payload(poi_count=2))

    assert response.status_code == 200
    data = response.json()
    assert len(calls) == 1
    assert data["mode"] == "walking"
    assert len(data["segments"]) == 1
    assert data["segments"][0]["segment_index"] == 1
    assert data["segments"][0]["from_poi_id"] == "poi_001"
    assert data["segments"][0]["to_poi_id"] == "poi_002"


def test_three_pois_generate_two_segments_and_totals(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = patch_route_client(
        monkeypatch,
        [
            route_result(
                mode=AmapRouteMode.WALKING,
                distance_m=2000,
                duration_s=1300,
                step_prefix="segment 1",
            ),
            route_result(
                mode=AmapRouteMode.WALKING,
                distance_m=3200,
                duration_s=2300,
                step_prefix="segment 2",
            ),
        ],
    )

    response = client.post("/api/route/chain", json=route_payload(poi_count=3))

    assert response.status_code == 200
    data = response.json()
    assert len(calls) == 2
    assert data["total_distance_m"] == 5200
    assert data["total_duration_s"] == 3600
    assert len(data["segments"]) == 2
    assert data["segments"][1]["segment_index"] == 2
    assert data["segments"][1]["from_poi_id"] == "poi_002"
    assert data["segments"][1]["to_poi_id"] == "poi_003"


def test_geojson_feature_collection_contains_one_feature_per_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_route_client(
        monkeypatch,
        [
            route_result(
                mode=AmapRouteMode.WALKING,
                distance_m=2000,
                duration_s=1300,
                step_prefix="segment 1",
            )
        ],
    )

    response = client.post("/api/route/chain", json=route_payload(poi_count=2))

    assert response.status_code == 200
    geojson = response.json()["geojson"]
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 2
    first_feature = geojson["features"][0]
    assert first_feature["type"] == "Feature"
    assert first_feature["geometry"]["type"] == "LineString"
    assert first_feature["geometry"]["coordinates"] == [
        [118.8012, 32.0735],
        [118.802, 32.074],
    ]
    assert first_feature["properties"]["segment_index"] == 1
    assert first_feature["properties"]["step_index"] == 1
    assert first_feature["properties"]["from_poi_id"] == "poi_001"
    assert first_feature["properties"]["to_poi_id"] == "poi_002"


def test_none_duration_is_counted_as_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_route_client(
        monkeypatch,
        [
            route_result(
                mode=AmapRouteMode.WALKING,
                distance_m=2000,
                duration_s=None,
                step_prefix="segment 1",
            )
        ],
    )

    response = client.post("/api/route/chain", json=route_payload(poi_count=2))

    assert response.status_code == 200
    data = response.json()
    assert data["segments"][0]["duration_s"] == 0
    assert data["total_duration_s"] == 0


def test_less_than_two_pois_returns_400() -> None:
    response = client.post("/api/route/chain", json=route_payload(poi_count=1))

    assert response.status_code == 400


def test_invalid_mode_returns_422() -> None:
    response = client.post(
        "/api/route/chain",
        json=route_payload(poi_count=2, mode="cycling"),
    )

    assert response.status_code == 422


def test_amap_upstream_error_returns_502(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeRouteClient:
        async def get_route(self, **kwargs: Any) -> AmapRouteResult:
            raise AmapUpstreamError(info="INVALID_USER_KEY", infocode="10001")

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(route_api, "AmapRouteClient", FakeRouteClient)

    response = client.post("/api/route/chain", json=route_payload(poi_count=2))

    assert response.status_code == 502
    assert response.json()["detail"]["info"] == "INVALID_USER_KEY"
    assert response.json()["detail"]["infocode"] == "10001"


def test_amap_config_error_does_not_expose_key(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeRouteClient:
        def __init__(self) -> None:
            raise AmapConfigError("secret-test-key should not leak")

    monkeypatch.setattr(route_api, "AmapRouteClient", FakeRouteClient)

    response = client.post("/api/route/chain", json=route_payload(poi_count=2))

    assert response.status_code == 500
    assert "secret-test-key" not in response.text


def test_health_still_passes() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

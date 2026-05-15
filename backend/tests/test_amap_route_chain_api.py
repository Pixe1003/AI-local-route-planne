from typing import Any

from fastapi.testclient import TestClient
import pytest

from app.api import routes_route
from app.main import app
from app.services.amap.errors import AmapConfigError, AmapUpstreamError
from app.services.amap.schemas import AmapRouteMode, AmapRouteResult, AmapRouteStep


client = TestClient(app)


def test_route_chain_requires_at_least_two_pois() -> None:
    response = client.post(
        "/api/route/chain",
        json={
            "mode": "driving",
            "poi_ids": ["sh_poi_001"],
        },
    )

    assert response.status_code == 400


def make_route_result(
    *,
    mode: AmapRouteMode = AmapRouteMode.DRIVING,
    distance_m: float,
    duration_s: float | None,
    prefix: str,
) -> AmapRouteResult:
    return AmapRouteResult(
        mode=mode,
        distance_m=distance_m,
        duration_s=duration_s,
        steps=[
            AmapRouteStep(
                instruction=f"{prefix} step 1",
                road_name=f"{prefix} road",
                distance_m=distance_m / 2,
                duration_s=None if duration_s is None else duration_s / 2,
                polyline_coordinates=[
                    [121.474, 31.232],
                    [121.48, 31.235],
                ],
            ),
            AmapRouteStep(
                instruction=f"{prefix} step 2",
                road_name=f"{prefix} road",
                distance_m=distance_m / 2,
                duration_s=None if duration_s is None else duration_s / 2,
                polyline_coordinates=[
                    [121.48, 31.235],
                    [121.49, 31.24],
                ],
            ),
        ],
        polyline_coordinates=[],
        raw_response={"status": "1"},
    )


def patch_route_client(
    monkeypatch: pytest.MonkeyPatch,
    results: list[AmapRouteResult],
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    class FakeRouteClient:
        def get_route(self, **kwargs: Any) -> AmapRouteResult:
            calls.append(kwargs)
            return results[len(calls) - 1]

        def close(self) -> None:
            return None

    monkeypatch.setattr(routes_route, "AmapRouteClient", FakeRouteClient, raising=False)
    return calls


def test_route_chain_resolves_seed_poi_ids_and_generates_segments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = patch_route_client(
        monkeypatch,
        [
            make_route_result(distance_m=1500, duration_s=600, prefix="segment 1"),
            make_route_result(distance_m=2500, duration_s=900, prefix="segment 2"),
        ],
    )

    response = client.post(
        "/api/route/chain",
        json={
            "mode": "driving",
            "poi_ids": ["sh_poi_001", "sh_poi_002", "sh_poi_003"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert len(calls) == 2
    assert calls[0]["mode"] == AmapRouteMode.DRIVING
    assert data["mode"] == "driving"
    assert [poi["id"] for poi in data["ordered_pois"]] == [
        "sh_poi_001",
        "sh_poi_002",
        "sh_poi_003",
    ]
    assert data["total_distance_m"] == 4000
    assert data["total_duration_s"] == 1500
    assert len(data["segments"]) == 2
    assert data["segments"][0]["from_poi_id"] == "sh_poi_001"
    assert data["segments"][0]["to_poi_id"] == "sh_poi_002"


def test_route_chain_outputs_one_geojson_feature_per_amap_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_route_client(
        monkeypatch,
        [make_route_result(distance_m=1500, duration_s=600, prefix="segment 1")],
    )

    response = client.post(
        "/api/route/chain",
        json={
            "mode": "driving",
            "poi_ids": ["sh_poi_001", "sh_poi_002"],
        },
    )

    assert response.status_code == 200
    geojson = response.json()["geojson"]
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 2
    first_feature = geojson["features"][0]
    assert first_feature["type"] == "Feature"
    assert first_feature["geometry"] == {
        "type": "LineString",
        "coordinates": [[121.474, 31.232], [121.48, 31.235]],
    }
    assert first_feature["properties"]["segment_index"] == 1
    assert first_feature["properties"]["step_index"] == 1
    assert first_feature["properties"]["from_poi_id"] == "sh_poi_001"
    assert first_feature["properties"]["to_poi_id"] == "sh_poi_002"


def test_route_chain_counts_missing_duration_as_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_route_client(
        monkeypatch,
        [make_route_result(distance_m=1500, duration_s=None, prefix="segment 1")],
    )

    response = client.post(
        "/api/route/chain",
        json={
            "mode": "driving",
            "poi_ids": ["sh_poi_001", "sh_poi_002"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["segments"][0]["duration_s"] == 0
    assert data["total_duration_s"] == 0


def test_route_chain_unknown_poi_id_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_route_client(monkeypatch, [])

    response = client.post(
        "/api/route/chain",
        json={
            "mode": "driving",
            "poi_ids": ["sh_poi_001", "missing_poi"],
        },
    )

    assert response.status_code == 404
    assert "missing_poi" in response.text


def test_route_chain_amap_upstream_error_returns_502(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeRouteClient:
        def get_route(self, **kwargs: Any) -> AmapRouteResult:
            raise AmapUpstreamError(info="INVALID_USER_KEY", infocode="10001")

        def close(self) -> None:
            return None

    monkeypatch.setattr(routes_route, "AmapRouteClient", FakeRouteClient, raising=False)

    response = client.post(
        "/api/route/chain",
        json={
            "mode": "driving",
            "poi_ids": ["sh_poi_001", "sh_poi_002"],
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"]["info"] == "INVALID_USER_KEY"
    assert response.json()["detail"]["infocode"] == "10001"


def test_route_chain_retries_transient_amap_upstream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    class FlakyRouteClient:
        def get_route(self, **kwargs: Any) -> AmapRouteResult:
            calls.append(kwargs)
            if len(calls) == 1:
                raise AmapUpstreamError(info="handshake operation timed out", infocode=None)
            return make_route_result(distance_m=1500, duration_s=600, prefix="segment 1")

        def close(self) -> None:
            return None

    monkeypatch.setattr(routes_route, "AmapRouteClient", FlakyRouteClient, raising=False)

    response = client.post(
        "/api/route/chain",
        json={
            "mode": "driving",
            "poi_ids": ["sh_poi_001", "sh_poi_002"],
        },
    )

    assert response.status_code == 200
    assert len(calls) == 2
    assert response.json()["total_distance_m"] == 1500


def test_route_chain_amap_config_error_does_not_expose_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRouteClient:
        def __init__(self) -> None:
            raise AmapConfigError("secret-key-value")

    monkeypatch.setattr(routes_route, "AmapRouteClient", FakeRouteClient, raising=False)

    response = client.post(
        "/api/route/chain",
        json={
            "mode": "driving",
            "poi_ids": ["sh_poi_001", "sh_poi_002"],
        },
    )

    assert response.status_code == 500
    assert "secret-key-value" not in response.text
    assert response.json()["detail"] == {
        "message": "Amap route client is not configured. Set AMAP_WEB_SERVICE_KEY or AMAP_KEY.",
        "code": "AMAP_CONFIG_MISSING",
    }

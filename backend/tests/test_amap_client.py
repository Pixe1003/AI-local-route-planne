import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx
import pytest

from app.services.amap.client import AmapRouteClient
from app.services.amap.errors import AmapConfigError, AmapUpstreamError
from app.services.amap.schemas import AmapLngLat, AmapRouteMode


T = TypeVar("T")


def run_async(callback: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(callback())


def make_route_response() -> dict:
    return {
        "status": "1",
        "info": "OK",
        "infocode": "10000",
        "route": {
            "paths": [
                {
                    "distance": "123.4",
                    "cost": {"duration": "56"},
                    "steps": [
                        {
                            "instruction": "Walk east",
                            "road_name": "Zhongshan Road",
                            "distance": "50",
                            "cost": {"duration": "20"},
                            "polyline": "118.8012,32.0735;118.8020,32.0740",
                        },
                        {
                            "instruction": "Continue",
                            "road": "Jiefang Road",
                            "distance": "73.4",
                            "duration": "36",
                            "polyline": "118.8020,32.0740;118.8030,32.0750",
                        },
                    ],
                }
            ]
        },
    }


def test_walking_request_path_and_params_are_correct() -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json=make_route_response())

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://restapi.amap.com",
        ) as http_client:
            client = AmapRouteClient(key="test-key", http_client=http_client)
            await client.get_route(
                mode=AmapRouteMode.WALKING,
                origin=AmapLngLat(longitude=118.8012, latitude=32.0735),
                destination=AmapLngLat(longitude=118.803, latitude=32.075),
            )

    run_async(scenario)

    assert captured_request is not None
    assert captured_request.url.path == "/v5/direction/walking"
    assert captured_request.url.params["key"] == "test-key"
    assert captured_request.url.params["origin"] == "118.8012,32.0735"
    assert captured_request.url.params["destination"] == "118.803,32.075"
    assert captured_request.url.params["show_fields"] == "cost,polyline,navi"


def test_driving_request_path_and_params_are_correct() -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json=make_route_response())

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://restapi.amap.com",
        ) as http_client:
            client = AmapRouteClient(key="test-key", http_client=http_client)
            await client.get_route(
                mode=AmapRouteMode.DRIVING,
                origin=AmapLngLat(longitude=118.8012, latitude=32.0735),
                destination=AmapLngLat(longitude=118.803, latitude=32.075),
            )

    run_async(scenario)

    assert captured_request is not None
    assert captured_request.url.path == "/v5/direction/driving"
    assert captured_request.url.params["key"] == "test-key"
    assert captured_request.url.params["origin"] == "118.8012,32.0735"
    assert captured_request.url.params["destination"] == "118.803,32.075"
    assert captured_request.url.params["show_fields"] == "cost,polyline,navi"


def test_missing_amap_web_service_key_raises_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AMAP_WEB_SERVICE_KEY", raising=False)

    with pytest.raises(AmapConfigError, match="AMAP_WEB_SERVICE_KEY"):
        AmapRouteClient()


def test_upstream_status_error_preserves_info_and_infocode() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "0",
                "info": "INVALID_USER_KEY",
                "infocode": "10001",
            },
        )

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://restapi.amap.com",
        ) as http_client:
            client = AmapRouteClient(key="test-key", http_client=http_client)
            with pytest.raises(AmapUpstreamError) as exc_info:
                await client.get_route(
                    mode=AmapRouteMode.WALKING,
                    origin=AmapLngLat(longitude=118.8012, latitude=32.0735),
                    destination=AmapLngLat(longitude=118.803, latitude=32.075),
                )

        assert exc_info.value.info == "INVALID_USER_KEY"
        assert exc_info.value.infocode == "10001"

    run_async(scenario)


def test_success_response_is_parsed_to_route_result() -> None:
    raw_response = make_route_response()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=raw_response)

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://restapi.amap.com",
        ) as http_client:
            client = AmapRouteClient(key="test-key", http_client=http_client)
            return await client.get_route(
                mode=AmapRouteMode.WALKING,
                origin=AmapLngLat(longitude=118.8012, latitude=32.0735),
                destination=AmapLngLat(longitude=118.803, latitude=32.075),
            )

    result = run_async(scenario)

    assert result.mode == AmapRouteMode.WALKING
    assert result.distance_m == 123.4
    assert result.duration_s == 56
    assert len(result.steps) == 2
    assert result.steps[0].instruction == "Walk east"
    assert result.steps[0].road_name == "Zhongshan Road"
    assert result.steps[0].distance_m == 50
    assert result.steps[0].duration_s == 20
    assert result.polyline_coordinates == [
        [118.8012, 32.0735],
        [118.802, 32.074],
        [118.802, 32.074],
        [118.803, 32.075],
    ]
    assert result.raw_response == raw_response

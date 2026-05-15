import json
import sqlite3
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np

from app.schemas.route import RouteChainRequest, RoutePoi
from app.services.amap.schemas import AmapRouteMode, AmapRouteResult, AmapRouteStep


def _route_result() -> AmapRouteResult:
    return AmapRouteResult(
        mode=AmapRouteMode.DRIVING,
        distance_m=1200,
        duration_s=600,
        steps=[
            AmapRouteStep(
                instruction="drive",
                road_name="demo road",
                distance_m=1200,
                duration_s=600,
                polyline_coordinates=[[117.22, 31.82], [117.23, 31.83]],
            )
        ],
        polyline_coordinates=[[117.22, 31.82], [117.23, 31.83]],
        raw_response={"status": "1"},
    )


def test_route_chain_uses_sqlite_segment_cache_across_clients(tmp_path, monkeypatch) -> None:
    from app.api import routes_route
    from app.services.amap import cache as amap_cache

    monkeypatch.setattr(amap_cache, "DB_PATH", tmp_path / "amap_cache.sqlite", raising=False)
    routes_route._SEGMENT_ROUTE_CACHE.clear()

    class FakeClient:
        def __init__(self) -> None:
            self.calls = 0

        def get_route(self, **kwargs: Any) -> AmapRouteResult:
            self.calls += 1
            return _route_result()

    payload = RouteChainRequest(mode=AmapRouteMode.DRIVING)
    route_pois = [
        RoutePoi(id="a", name="A", longitude=117.22, latitude=31.82, category="restaurant"),
        RoutePoi(id="b", name="B", longitude=117.23, latitude=31.83, category="culture"),
    ]

    first_client = FakeClient()
    routes_route.build_route_chain(payload=payload, route_pois=route_pois, client=first_client)
    assert first_client.calls == 1

    routes_route._SEGMENT_ROUTE_CACHE.clear()
    second_client = FakeClient()
    routes_route.build_route_chain(payload=payload, route_pois=route_pois, client=second_client)

    assert second_client.calls == 0
    with sqlite3.connect(tmp_path / "amap_cache.sqlite") as conn:
        row = conn.execute("SELECT COUNT(*), SUM(hit_count) FROM amap_segments").fetchone()
    assert row == (1, 1)


def test_llm_tool_call_cache_reuses_successful_response(monkeypatch) -> None:
    from app.llm import cache as llm_cache
    from app.llm.client import LlmClient

    llm_cache.clear()
    calls = 0

    def fake_settings():
        return SimpleNamespace(
            llm_api_key="test-key",
            llm_base_url="https://api.example.com/v1",
            llm_auth_header="authorization",
            llm_model="test-model",
            llm_provider="test-provider",
            llm_timeout_seconds=12,
        )

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
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
                "usage": {"total_tokens": 9},
            }

    def fake_post(*args: Any, **kwargs: Any) -> FakeResponse:
        nonlocal calls
        calls += 1
        return FakeResponse()

    monkeypatch.setattr("app.llm.client.get_settings", fake_settings)
    monkeypatch.setattr("app.llm.client.httpx.post", fake_post)

    first = LlmClient().complete_tool_call(
        "choose",
        tools=[{"name": "parse_intent", "parameters": {"type": "object"}}],
        fallback={"tool": "finish", "args": {}},
    )
    second = LlmClient().complete_tool_call(
        "choose",
        tools=[{"name": "parse_intent", "parameters": {"type": "object"}}],
        fallback={"tool": "finish", "args": {}},
    )

    assert calls == 1
    assert first == {"tool": "parse_intent", "args": {"free_text": "local food"}, "_tokens_used": 9}
    assert second == {"tool": "parse_intent", "args": {"free_text": "local food"}, "_tokens_used": 0}


def test_llm_tool_call_cache_does_not_cache_fallback(monkeypatch) -> None:
    from app.llm import cache as llm_cache
    from app.llm.client import LlmClient

    llm_cache.clear()
    calls = 0

    def fake_settings():
        return SimpleNamespace(
            llm_api_key="test-key",
            llm_base_url="https://api.example.com/v1",
            llm_auth_header="authorization",
            llm_model="test-model",
            llm_provider="test-provider",
            llm_timeout_seconds=12,
        )

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {}}], "usage": {"total_tokens": 9}}

    def fake_post(*args: Any, **kwargs: Any) -> FakeResponse:
        nonlocal calls
        calls += 1
        return FakeResponse()

    monkeypatch.setattr("app.llm.client.get_settings", fake_settings)
    monkeypatch.setattr("app.llm.client.httpx.post", fake_post)

    fallback = {"tool": "finish", "args": {}}
    assert LlmClient().complete_tool_call("choose", tools=[], fallback=fallback) == fallback
    assert LlmClient().complete_tool_call("choose", tools=[], fallback=fallback) == fallback
    assert calls == 2


def test_ugc_query_embedding_cache_reuses_same_query(tmp_path, monkeypatch) -> None:
    from app.repositories import embedding_cache
    from app.repositories.ugc_vector_repo import UgcVectorRepo

    embedding_cache.clear()
    data_path = tmp_path / "reviews.jsonl"
    data_path.write_text("", encoding="utf-8")
    embed_path = tmp_path / "embeddings.npy"
    np.save(embed_path, np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype="float32"))
    meta_path = tmp_path / "meta.jsonl"
    meta_path.write_text(
        "\n".join(
            [
                json.dumps({"post_id": "p1", "poi_id": "poi_1", "content": "one", "city": "hefei"}),
                json.dumps({"post_id": "p2", "poi_id": "poi_2", "content": "two", "city": "hefei"}),
            ]
        ),
        encoding="utf-8",
    )

    class FakeModel:
        def __init__(self) -> None:
            self.calls = 0

        def encode(self, text: str, normalize_embeddings: bool = True):
            self.calls += 1
            return np.asarray([1.0, 0.0], dtype="float32")

    fake_model = FakeModel()
    monkeypatch.setattr("app.repositories.ugc_vector_repo.SentenceTransformer", lambda name: fake_model)

    repo = UgcVectorRepo(data_path=data_path, embed_path=embed_path, meta_path=meta_path)
    assert repo.search("same query", city="hefei", top_k=1)[0].poi_id == "poi_1"
    assert repo.search("same query", city="hefei", top_k=1)[0].poi_id == "poi_1"
    assert fake_model.calls == 1


def test_session_vector_query_embedding_cache_reuses_same_text(tmp_path, monkeypatch) -> None:
    from app.repositories import embedding_cache
    from app.repositories.session_vector_repo import SessionVectorRepo

    embedding_cache.clear()

    class FakeModel:
        def __init__(self) -> None:
            self.calls = 0

        def encode(self, text: str, normalize_embeddings: bool = True):
            self.calls += 1
            return np.asarray([1.0, 0.0], dtype="float32")

    fake_model = FakeModel()
    module = ModuleType("sentence_transformers")
    module.SentenceTransformer = lambda *args, **kwargs: fake_model
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)

    repo = SessionVectorRepo(tmp_path)
    first = repo._encode("same text")
    second = repo._encode("same text")

    assert np.array_equal(first, second)
    assert fake_model.calls == 1

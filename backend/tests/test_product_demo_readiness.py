import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.schemas.poi import HighlightQuote, PoiDetail


class FakeEmbedder:
    terms = ["拍照", "出片", "老人", "排队", "profile", "review"]

    def embed_documents(self, texts: list[str]):
        return np.asarray([self._vector(text) for text in texts], dtype="float32")

    def embed_query(self, text: str):
        return np.asarray(self._vector(text), dtype="float32")

    def _vector(self, text: str) -> list[float]:
        lowered = text.lower()
        return [float(lowered.count(term.lower())) for term in self.terms]


def _poi(
    poi_id: str,
    *,
    category: str = "scenic",
    lat: float = 31.8206,
    lng: float = 117.2272,
) -> PoiDetail:
    return PoiDetail(
        id=poi_id,
        name=f"{poi_id} name",
        city="hefei",
        category=category,
        sub_category="公园" if category == "scenic" else "徽菜",
        address="合肥测试地址",
        latitude=lat,
        longitude=lng,
        rating=4.7,
        price_per_person=50,
        open_hours={"monday": [{"open": "10:00", "close": "22:00"}]},
        tags=[category, "拍照", "少排队"],
        cover_image=None,
        review_count=120,
        queue_estimate={"weekday_peak": 8, "weekend_peak": 12},
        visit_duration=50,
        best_time_slots=[],
        avoid_time_slots=[],
        highlight_quotes=[
            HighlightQuote(quote="适合拍照，也适合带老人慢慢逛。", source="ugc", category="ugc_review")
        ],
        high_freq_keywords=[{"keyword": "拍照", "count": 20}],
        hidden_menu=[],
        avoid_tips=[],
        suitable_for=["friends"],
        atmosphere=["relaxed"],
    )


class PoolRepo:
    def __init__(self, pois: list[PoiDetail]) -> None:
        self._pois = {poi.id: poi for poi in pois}

    def get(self, poi_id: str) -> PoiDetail:
        return self._pois[poi_id]

    def get_many(self, poi_ids):
        return [self._pois[poi_id] for poi_id in poi_ids if poi_id in self._pois]

    def list_by_city(self, city: str, limit: int | None = None):
        pois = [poi for poi in self._pois.values() if poi.city == city]
        return pois[:limit] if limit else pois


class StaticRetrievalService:
    def __init__(self, poi_ids: list[str]) -> None:
        self.poi_ids = poi_ids

    def retrieve_with_stats(self, request, limit: int = 300):
        return SimpleNamespace(
            poi_ids=self.poi_ids[:limit],
            stats={"total_candidates": len(self.poi_ids), "fts_candidates": 0, "bucket_candidates": 0},
        )

    def evidence_for_poi(self, poi_id: str, query: str | None = None) -> str | None:
        return None


class EmptySemanticRetrieval:
    def retrieve(self, query):
        return []


def test_health_exposes_ready_and_degraded_subsystem_status(monkeypatch, tmp_path):
    from app import main

    settings = SimpleNamespace(
        app_name="local-route-agent",
        rag_enabled=True,
        faiss_index_path=str(tmp_path / "missing-faiss"),
        amap_web_service_key="amap-key",
        amap_key="",
        amap_route_base_url="https://restapi.amap.com",
    )
    monkeypatch.setattr(main, "settings", settings)

    payload = main.health()

    assert payload["rag"]["status"] == "degraded"
    assert payload["faiss"]["status"] == "missing_index"
    assert payload["amap"]["status"] == "ready"
    assert payload["memory"]["status"] in {"ready", "degraded"}
    assert payload["cache"]["status"] == "ready"


def test_pool_applies_origin_radius_and_outputs_distance_meters():
    from app.schemas.pool import PoolRequest
    from app.services.pool_service import PoolService

    near = _poi("near_scenic", lat=31.8206, lng=117.2272)
    far = _poi("far_scenic", lat=32.9, lng=118.5)
    service = PoolService(
        repo=PoolRepo([near, far]),
        retrieval_service=StaticRetrievalService(["near_scenic", "far_scenic"]),
        semantic_retrieval=EmptySemanticRetrieval(),
    )

    pool = service.generate_pool(
        PoolRequest(
            user_id="u1",
            city="hefei",
            free_text="少排队拍照",
            origin_latitude=31.8206,
            origin_longitude=117.2272,
            radius_meters=3_000,
        )
    )

    pooled = [poi for category in pool.categories for poi in category.pois]
    assert [poi.id for poi in pooled] == ["near_scenic"]
    assert pooled[0].distance_meters == 0
    assert pool.meta.data_warning == "FAISS index missing; using SQLite/seed fallback."


def test_pool_uses_profile_origin_when_top_level_origin_is_omitted():
    from app.schemas.onboarding import DestinationProfile, UserNeedProfile
    from app.schemas.pool import PoolRequest
    from app.services.pool_service import PoolService

    near = _poi("near_scenic", lat=31.7994, lng=117.2906)
    far = _poi("far_scenic", lat=32.9, lng=118.5)
    profile = UserNeedProfile(
        destination=DestinationProfile(
            city="hefei",
            start_latitude=31.7994,
            start_longitude=117.2906,
            radius_meters=3_000,
        )
    )
    service = PoolService(
        repo=PoolRepo([near, far]),
        retrieval_service=StaticRetrievalService(["near_scenic", "far_scenic"]),
        semantic_retrieval=EmptySemanticRetrieval(),
    )

    pool = service.generate_pool(PoolRequest(user_id="u1", city="hefei", need_profile=profile))

    pooled = [poi for category in pool.categories for poi in category.pois]
    assert [poi.id for poi in pooled] == ["near_scenic"]
    assert pooled[0].distance_meters == 0


def test_need_profile_round_trips_origin_through_plan_context():
    from app.schemas.onboarding import UserNeedProfile
    from app.schemas.plan import PlanContext
    from app.schemas.pool import TimeWindow

    context = PlanContext(
        city="hefei",
        date="2026-05-25",
        time_window=TimeWindow(start="14:00", end="20:00"),
        origin_latitude=31.8682,
        origin_longitude=117.2952,
        radius_meters=6_000,
    )

    profile = UserNeedProfile.from_plan_context(context, raw_query="少排队")
    round_tripped = profile.to_plan_context()

    assert profile.destination.start_latitude == 31.8682
    assert profile.destination.start_longitude == 117.2952
    assert profile.destination.radius_meters == 6_000
    assert round_tripped.origin_latitude == 31.8682
    assert round_tripped.origin_longitude == 117.2952
    assert round_tripped.radius_meters == 6_000


def test_hefei_pool_request_gets_default_demo_origin_when_absent():
    from app.schemas.pool import PoolRequest
    from app.services.location_context import origin_from_request, radius_from_request

    request = PoolRequest(user_id="u1", city="hefei")

    assert origin_from_request(request) == (31.8206, 117.2272)
    assert radius_from_request(request) is None


def test_pool_score_does_not_apply_distance_penalty_twice():
    from app.schemas.pool import PoolRequest
    from app.services.location_context import plan_context_from_pool_request
    from app.services.pool_service import PoolService

    near = _poi("near_scenic", lat=31.8206, lng=117.2272)
    far = _poi("far_scenic", lat=32.9, lng=118.5)
    request = PoolRequest(user_id="u1", city="hefei", origin_latitude=31.8206, origin_longitude=117.2272)
    service = PoolService(
        repo=PoolRepo([near, far]),
        retrieval_service=StaticRetrievalService(["far_scenic"]),
        semantic_retrieval=EmptySemanticRetrieval(),
    )
    service.vector_repo.score = lambda *args, **kwargs: 0.0

    context = plan_context_from_pool_request(request, "hefei")
    near_score = service._score_poi(
        near,
        persona_tags=[],
        free_text=None,
        budget_per_person=None,
        request=request,
        context=context,
    )
    far_score = service._score_poi(
        far,
        persona_tags=[],
        free_text=None,
        budget_per_person=None,
        request=request,
        context=context,
    )

    assert near_score - far_score == pytest.approx(0.18)


def test_estimate_transport_uses_amap_when_available(monkeypatch):
    from app.services.amap.schemas import AmapRouteMode, AmapRouteResult
    from app.solver import distance as distance_module

    calls = []

    class FakeAmapRouteClient:
        def get_route(self, **kwargs):
            calls.append(kwargs)
            return AmapRouteResult(
                mode=AmapRouteMode.DRIVING,
                distance_m=3210,
                duration_s=660,
                steps=[],
                polyline_coordinates=[],
                raw_response={"status": "1"},
            )

        def close(self):
            return None

    monkeypatch.setattr(distance_module, "AmapRouteClient", FakeAmapRouteClient, raising=False)

    transport = distance_module.estimate_transport(_poi("a"), _poi("b", lat=31.9, lng=117.35))

    assert calls
    assert transport.mode == "driving"
    assert transport.distance_meters == 3210
    assert transport.duration_min == 11
    assert transport.source == "amap"


def test_estimate_transport_falls_back_to_haversine_when_amap_unavailable(monkeypatch):
    from app.services.amap.errors import AmapConfigError
    from app.solver import distance as distance_module

    class MissingAmapRouteClient:
        def __init__(self):
            raise AmapConfigError("missing key")

    monkeypatch.setattr(distance_module, "AmapRouteClient", MissingAmapRouteClient, raising=False)

    transport = distance_module.estimate_transport(_poi("a"), _poi("b", lat=31.9, lng=117.35))

    assert transport.distance_meters > 0
    assert transport.duration_min > 0
    assert transport.source == "fallback"


def test_agent_run_request_origin_is_carried_into_initial_context():
    from app.api.routes_agent import AgentRunRequest, build_initial_state
    from app.schemas.pool import TimeWindow

    state = build_initial_state(
        AgentRunRequest(
            user_id="u1",
            free_text="少排队拍照",
            city="hefei",
            date="2026-05-25",
            time_window=TimeWindow(start="14:00", end="20:00"),
            budget_per_person=180,
            origin_latitude=31.8206,
            origin_longitude=117.2272,
            radius_meters=8000,
        )
    )

    assert state.context.origin_latitude == 31.8206
    assert state.context.origin_longitude == 117.2272
    assert state.context.radius_meters == 8000
    assert state.profile.destination.start_latitude == 31.8206
    assert state.profile.destination.start_longitude == 117.2272
    assert state.profile.destination.radius_meters == 8000


def test_agent_run_request_uses_profile_origin_when_top_level_origin_is_missing():
    from app.api.routes_agent import AgentRunRequest, build_initial_state
    from app.schemas.onboarding import DestinationProfile, UserNeedProfile
    from app.schemas.pool import TimeWindow

    profile = UserNeedProfile(
        destination=DestinationProfile(
            city="hefei",
            start_latitude=31.7994,
            start_longitude=117.2906,
            radius_meters=5_000,
        )
    )

    state = build_initial_state(
        AgentRunRequest(
            user_id="u1",
            free_text="少排队拍照",
            city="hefei",
            date="2026-05-25",
            time_window=TimeWindow(start="14:00", end="20:00"),
            need_profile=profile,
        )
    )

    assert state.context.origin_latitude == 31.7994
    assert state.context.origin_longitude == 117.2906
    assert state.context.radius_meters == 5_000
    assert state.profile.destination.start_latitude == 31.7994
    assert state.profile.destination.start_longitude == 117.2906
    assert state.profile.destination.radius_meters == 5_000


def test_build_faiss_rag_can_require_real_sqlite_data(tmp_path):
    from scripts.build_faiss_rag import build_faiss_rag

    with pytest.raises(FileNotFoundError, match="real SQLite POI data"):
        build_faiss_rag(
            city="hefei",
            index_dir=tmp_path / "faiss",
            sqlite_path=tmp_path / "missing.sqlite",
            require_real_data=True,
            embedder=FakeEmbedder(),
        )


def test_real_hefei_data_smoke_when_configured():
    data_dir = _real_data_dir()
    db_path = data_dir / "hefei_pois.sqlite"
    ugc_path = data_dir / "ugc_hefei.jsonl"
    assert db_path.exists(), f"missing real DB: {db_path}"
    assert ugc_path.exists(), f"missing real UGC JSONL: {ugc_path}"

    with sqlite3.connect(db_path) as conn:
        app_pois = conn.execute("SELECT COUNT(*) FROM app_pois").fetchone()[0]
        evidence = conn.execute("SELECT COUNT(*) FROM ugc_evidence_index").fetchone()[0]
        missing_coords = conn.execute(
            """
            SELECT COUNT(*)
            FROM app_pois
            WHERE latitude IS NULL OR longitude IS NULL OR latitude = 0 OR longitude = 0
            """
        ).fetchone()[0]

    from app.repositories.sqlite_poi_repo import load_sqlite_pois

    pois = load_sqlite_pois(db_path, city="hefei", limit=160)
    categories = {poi.category for poi in pois}

    assert app_pois >= 100
    assert evidence >= 100
    assert missing_coords == 0
    assert pois
    assert categories - {"restaurant"}


def test_real_hefei_faiss_smoke_when_configured(tmp_path):
    data_dir = _real_data_dir()
    db_path = data_dir / "hefei_pois.sqlite"

    from app.repositories.faiss_index import FaissVectorIndex
    from app.repositories.faiss_meta import FaissMetaStore
    from scripts.build_faiss_rag import build_faiss_rag

    index_dir = tmp_path / "faiss"
    stats = build_faiss_rag(
        city="hefei",
        index_dir=index_dir,
        sqlite_path=db_path,
        require_real_data=True,
        limit=160,
        embedder=FakeEmbedder(),
    )
    rows = FaissVectorIndex(index_dir, embedder=FakeEmbedder()).query(
        text="少排队 拍照 带老人",
        city="hefei",
        top_k=5,
        source_types=["ugc_review"],
    )
    source_types = {
        row["source_type"]
        for row in FaissMetaStore(index_dir / "meta.jsonl").read()
    }

    assert stats["pois"] > 0
    assert stats["real_sqlite_rows"] > 0
    assert stats["documents"] > stats["pois"]
    assert {"poi_profile", "ugc_review"} <= source_types
    assert rows
    assert rows[0]["text"]


def _real_data_dir() -> Path:
    raw_path = os.getenv("AIROUTE_REAL_DATA_DIR")
    if not raw_path:
        pytest.skip("set AIROUTE_REAL_DATA_DIR to run real Hefei data smoke tests")
    return Path(raw_path)

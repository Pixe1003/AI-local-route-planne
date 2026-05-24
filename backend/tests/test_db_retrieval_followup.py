from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.seed_data import OPEN_HOURS
from app.schemas.poi import HighlightQuote, PoiDetail


def _poi(
    poi_id: str,
    *,
    city: str = "hefei",
    category: str = "scenic",
    lat: float = 31.82,
    lng: float = 117.29,
    tags: list[str] | None = None,
) -> PoiDetail:
    return PoiDetail(
        id=poi_id,
        name=f"{poi_id} name",
        city=city,
        category=category,
        sub_category=category,
        address="合肥市测试地址",
        latitude=lat,
        longitude=lng,
        rating=4.6,
        price_per_person=50,
        open_hours=OPEN_HOURS,
        tags=tags or [category, "低排队"],
        cover_image=None,
        review_count=100,
        queue_estimate={"weekday_peak": 8, "weekend_peak": 12},
        visit_duration=50,
        best_time_slots=["weekend_afternoon"],
        avoid_time_slots=[],
        highlight_quotes=[HighlightQuote(quote="适合散步拍照。", source="ugc")],
        high_freq_keywords=[{"keyword": category, "count": 80}],
        hidden_menu=[],
        avoid_tips=[],
        suitable_for=["friends"],
        atmosphere=["relaxed"],
    )


class EmptyRepo:
    def list_by_city(self, city: str, limit: int | None = None):
        return []

    def get_many(self, poi_ids):
        return []


class NoopRetrieval:
    def retrieve(self, query):
        return []


def test_pool_does_not_fallback_to_shanghai_when_city_has_no_data():
    from app.schemas.pool import PoolRequest
    from app.services.pool_service import PoolService

    pool = PoolService(repo=EmptyRepo(), retrieval_service=NoopRetrieval()).generate_pool(
        PoolRequest(user_id="mock_user", city="hefei", free_text="合肥公园散步")
    )

    assert pool.categories == []
    assert pool.default_selected_ids == []
    assert pool.meta.data_warning == "city_data_unavailable"


class TrackingRepo(EmptyRepo):
    def __init__(self):
        self.cities = []

    def list_by_city(self, city: str, limit: int | None = None):
        self.cities.append(city)
        return []


def test_solver_does_not_query_shanghai_when_target_city_has_no_data():
    from app.schemas.plan import HardConstraints, SoftPreferences, StructuredIntent
    from app.services.solver_service import SolverService

    repo = TrackingRepo()
    intent = StructuredIntent(
        hard_constraints=HardConstraints(start_time="14:00", end_time="18:00"),
        soft_preferences=SoftPreferences(),
        must_visit_pois=[],
    )

    SolverService(repo=repo)._ensure_minimum_candidates([], "hefei", intent)

    assert repo.cities == ["hefei"]


def test_health_exposes_rag_status():
    payload = TestClient(app).get("/health").json()

    assert "rag" in payload
    assert {"enabled", "index_exists", "collection_count", "embedding_configured"} <= set(payload["rag"])


class FakeVectorIndex:
    def query(self, *, text, city, top_k, category_filters=None, source_types=None):
        del text, city, top_k, category_filters, source_types
        return [
            {
                "poi_id": "near",
                "score": 0.9,
                "doc_id": "poi_profile:near",
                "source_type": "poi_profile",
                "text": "near",
                "metadata": {"city": "hefei", "category": "scenic"},
            },
            {
                "poi_id": "far",
                "score": 0.95,
                "doc_id": "poi_profile:far",
                "source_type": "poi_profile",
                "text": "far",
                "metadata": {"city": "hefei", "category": "scenic"},
            },
        ]


class DistanceRepo:
    def __init__(self):
        self.pois = {
            "near": _poi("near", lat=31.82, lng=117.29),
            "far": _poi("far", lat=32.9, lng=118.5),
        }

    def get(self, poi_id: str):
        return self.pois[poi_id]


def test_retrieval_filters_radius_from_origin():
    from app.schemas.rag import RetrievalQuery
    from app.services.retrieval_service import RetrievalService

    results = RetrievalService(repo=DistanceRepo(), vector_index=FakeVectorIndex()).retrieve(
        RetrievalQuery(
            city="hefei",
            text="公园散步",
            top_k=5,
            origin_latitude=31.82,
            origin_longitude=117.29,
            radius_meters=5000,
        )
    )

    assert [item.poi_id for item in results] == ["near"]


def test_distance_penalty_prefers_nearby_poi():
    from app.schemas.plan import PlanContext
    from app.schemas.pool import TimeWindow
    from app.services.poi_scoring_service import PoiScoringService

    context = PlanContext(
        city="hefei",
        date="2026-05-02",
        time_window=TimeWindow(start="14:00", end="18:00"),
        origin_latitude=31.82,
        origin_longitude=117.29,
    )
    scorer = PoiScoringService()

    near = scorer.score_poi(_poi("near", lat=31.82, lng=117.29), context=context)
    far = scorer.score_poi(_poi("far", lat=32.9, lng=118.5), context=context)

    assert near.distance_penalty == 0
    assert far.distance_penalty < near.distance_penalty
    assert near.total > far.total


def test_missing_open_hours_emits_warning_not_error():
    from app.schemas.plan import HardConstraints, RouteMetrics, RouteSkeleton, RouteStop, SoftPreferences, StructuredIntent
    from app.services.route_validator import RouteValidator

    poi = _poi("unknown_hours")
    poi.open_hours = {}

    class Repo:
        def get_many(self, poi_ids):
            return [poi for _ in poi_ids]

        def get(self, poi_id):
            return poi

    route = RouteSkeleton(
        style="relaxed",
        stops=[
            RouteStop(poi_id="unknown_hours", arrival_time="14:00", departure_time="14:50", duration_min=50),
            RouteStop(poi_id="unknown_hours", arrival_time="15:00", departure_time="15:50", duration_min=50),
            RouteStop(poi_id="unknown_hours", arrival_time="16:00", departure_time="16:50", duration_min=50),
        ],
        dropped_poi_ids=[],
        drop_reasons={},
        metrics=RouteMetrics(
            total_duration_min=170,
            total_cost=0,
            poi_count=3,
            walking_distance_meters=0,
            queue_total_min=0,
        ),
    )
    intent = StructuredIntent(
        hard_constraints=HardConstraints(start_time="14:00", end_time="18:00"),
        soft_preferences=SoftPreferences(),
        must_visit_pois=[],
    )

    result = RouteValidator(repo=Repo()).validate(route, intent)

    assert result.is_valid is True
    assert "opening_hours_unknown" in {issue.code for issue in result.issues}


def test_embedding_client_caches_same_query(monkeypatch):
    from app.llm.embedding import EmbeddingClient

    calls = {"count": 0}

    def fake_embed_texts(self, texts):
        calls["count"] += 1
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(EmbeddingClient, "embed_texts", fake_embed_texts)
    EmbeddingClient.clear_query_cache()
    client = EmbeddingClient()

    assert client.embed_query("合肥公园散步") == [1.0, 0.0]
    assert client.embed_query("合肥公园散步") == [1.0, 0.0]
    assert calls["count"] == 1


def test_chroma_where_includes_category_and_source_filters():
    from app.repositories.rag_index import _query_where

    where = _query_where(
        city="hefei",
        source_types=["ugc_review"],
        category_filters=["scenic", "culture"],
    )

    assert where == {
        "$and": [
            {"city": "hefei"},
            {"source_type": {"$in": ["ugc_review"]}},
            {"category": {"$in": ["scenic", "culture"]}},
        ]
    }


def test_vector_repo_matches_synonyms_and_tags():
    from app.repositories.vector_repo import VectorRepository

    poi = _poi("senior_walk", tags=["公园", "平缓", "适合老人", "安静"])

    assert VectorRepository().score(poi, [], "带老人散步") > 0.2


def test_real_sqlite_file_uses_canonical_name_and_core_tables_exist():
    db_path = Path("data/processed/hefei_pois.sqlite")
    legacy_path = Path("data/processed/hefei_pois .sqlite")
    if not db_path.exists() and not legacy_path.exists():
        pytest.skip("real hefei sqlite fixture is not present")

    assert db_path.exists()
    assert not legacy_path.exists()

    import sqlite3

    con = sqlite3.connect(db_path)
    try:
        app_count = con.execute("select count(*) from app_pois").fetchone()[0]
        feature_count = con.execute("select count(*) from poi_feature_index").fetchone()[0]
        ugc_count = con.execute("select count(*) from ugc_evidence_index").fetchone()[0]
        derived = {
            row[0]: row[1]
            for row in con.execute(
                "select derived_category, count(*) from poi_feature_index group by derived_category"
            )
        }
    finally:
        con.close()

    assert app_count > 1000
    assert feature_count >= app_count
    assert ugc_count > app_count
    assert derived.get("restaurant", 0) > 0
    assert any(count > 0 for category, count in derived.items() if category != "restaurant")

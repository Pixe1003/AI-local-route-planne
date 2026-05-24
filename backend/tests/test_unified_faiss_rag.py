import numpy as np
import json
import sqlite3

from app.repositories.seed_data import load_seed_pois
from app.schemas.poi import HighlightQuote, PoiDetail


class FakeEmbedder:
    terms = ["profile", "review", "photo", "quiet", "food", "park"]

    def embed_documents(self, texts: list[str]):
        return np.asarray([self._vector(text) for text in texts], dtype="float32")

    def embed_query(self, text: str):
        return np.asarray(self._vector(text), dtype="float32")

    def _vector(self, text: str) -> list[float]:
        lowered = text.lower()
        return [float(lowered.count(term)) for term in self.terms]


def _poi(poi_id: str, category: str = "scenic", *, lat: float = 31.82, lng: float = 117.29) -> PoiDetail:
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
        tags=[category, "photo", "quiet"],
        cover_image=None,
        review_count=120,
        queue_estimate={"weekday_peak": 8, "weekend_peak": 12},
        visit_duration=50,
        best_time_slots=[],
        avoid_time_slots=[],
        highlight_quotes=[
            HighlightQuote(quote="review quiet photo park evidence", source="ugc", category="ugc_review")
        ],
        high_freq_keywords=[{"keyword": "photo", "count": 20}],
        hidden_menu=[],
        avoid_tips=[],
        suitable_for=["friends"],
        atmosphere=["relaxed"],
    )


class Repo:
    def __init__(self, pois: list[PoiDetail]) -> None:
        self._pois = {poi.id: poi for poi in pois}

    def get(self, poi_id: str) -> PoiDetail:
        return self._pois[poi_id]

    def get_many(self, poi_ids):
        return [self._pois[poi_id] for poi_id in poi_ids if poi_id in self._pois]


def test_faiss_index_filters_sidecar_metadata_and_returns_source_rows(tmp_path):
    from app.repositories.faiss_index import FaissVectorIndex
    from app.repositories.rag_build import build_poi_document, build_ugc_documents, write_faiss_index

    scenic = _poi("hf_scenic", "scenic")
    food = _poi("hf_food", "restaurant")
    documents = [build_poi_document(scenic), *build_ugc_documents(scenic), build_poi_document(food)]

    write_faiss_index(documents, tmp_path, embedder=FakeEmbedder())
    rows = FaissVectorIndex(tmp_path, embedder=FakeEmbedder()).query(
        text="quiet photo review",
        city="hefei",
        top_k=5,
        category_filters=["scenic"],
        source_types=["ugc_review"],
    )

    assert rows
    assert {row["poi_id"] for row in rows} == {"hf_scenic"}
    assert {row["source_type"] for row in rows} == {"ugc_review"}
    assert rows[0]["metadata"]["category"] == "scenic"


def test_retrieval_service_aggregates_faiss_profile_and_ugc_sources(tmp_path):
    from app.repositories.faiss_index import FaissVectorIndex
    from app.repositories.rag_build import build_poi_document, build_ugc_documents, write_faiss_index
    from app.schemas.rag import RetrievalQuery
    from app.services.retrieval_service import RetrievalService

    scenic = _poi("hf_scenic", "scenic")
    write_faiss_index(
        [build_poi_document(scenic), *build_ugc_documents(scenic)],
        tmp_path,
        embedder=FakeEmbedder(),
    )

    results = RetrievalService(
        repo=Repo([scenic]),
        vector_index=FaissVectorIndex(tmp_path, embedder=FakeEmbedder()),
    ).retrieve(
        RetrievalQuery(
            city="hefei",
            text="quiet photo review",
            source_types=["poi_profile", "ugc_review"],
            top_k=3,
        )
    )

    assert [item.poi_id for item in results] == ["hf_scenic"]
    assert {"semantic_poi_profile", "semantic_ugc_review"} <= set(results[0].provenance)
    assert [snippet.source_type for snippet in results[0].evidence_snippets] == [
        "ugc_review",
        "poi_profile",
    ]


def test_hefei_seed_fallback_keeps_agent_routes_available_without_sqlite():
    hefei_pois = [poi for poi in load_seed_pois() if poi.city == "hefei"]

    assert len(hefei_pois) >= 24
    assert {"hf_poi_061581", "hf_poi_035366", "hf_poi_020889"} <= {poi.id for poi in hefei_pois}
    assert any(poi.category == "restaurant" for poi in hefei_pois)


class FakeSemanticRetrieval:
    def __init__(self) -> None:
        self.calls = []

    def retrieve(self, query):
        from app.schemas.rag import EvidenceSnippet, RetrievedPoi

        self.calls.append(query)
        if query.source_types == ["ugc_review"]:
            return [
                RetrievedPoi(
                    poi_id="hf_scenic",
                    score=0.93,
                    evidence_snippets=[
                        EvidenceSnippet(
                            doc_id="ugc_review:hf_scenic:0",
                            source_type="ugc_review",
                            text="review quiet photo park evidence",
                            score=0.93,
                        )
                    ],
                    provenance=["semantic_ugc_review"],
                )
            ]
        if query.source_types == ["poi_profile"]:
            return [
                RetrievedPoi(
                    poi_id="hf_food",
                    score=0.88,
                    evidence_snippets=[
                        EvidenceSnippet(
                            doc_id="poi_profile:hf_food",
                            source_type="poi_profile",
                            text="profile food low queue",
                            score=0.88,
                        )
                    ],
                    provenance=["semantic_poi_profile"],
                )
            ]
        return []


class PoolRepo(Repo):
    def list_by_city(self, city: str, limit: int | None = None):
        pois = [poi for poi in self._pois.values() if poi.city == city]
        return pois[:limit] if limit else pois

    def get_many(self, poi_ids):
        return [self._pois[poi_id] for poi_id in poi_ids if poi_id in self._pois]


def test_pool_service_keeps_semantic_provenance_and_evidence():
    from app.schemas.pool import PoolRequest
    from app.services.pool_service import PoolService

    repo = PoolRepo([_poi("hf_scenic", "scenic"), _poi("hf_food", "restaurant")])
    semantic = FakeSemanticRetrieval()

    pool = PoolService(repo=repo, semantic_retrieval=semantic).generate_pool(
        PoolRequest(user_id="u1", city="hefei", free_text="quiet photo and food")
    )

    pooled = [poi for category in pool.categories for poi in category.pois]
    scenic = next(poi for poi in pooled if poi.id == "hf_scenic")

    assert ["poi_profile"] in [call.source_types for call in semantic.calls]
    assert ["ugc_review"] in [call.source_types for call in semantic.calls]
    assert scenic.retrieval_provenance == ["semantic_ugc_review"]
    assert scenic.evidence_snippets[0].source_type == "ugc_review"
    assert scenic.highlight_quote == "review quiet photo park evidence"


def test_sqlite_loader_uses_derived_category_and_ugc_evidence(tmp_path):
    from app.repositories.sqlite_poi_repo import load_sqlite_pois

    db_path = tmp_path / "hefei_pois.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_pois (
              id TEXT PRIMARY KEY, name TEXT, city TEXT, category TEXT, sub_category TEXT,
              address TEXT, latitude REAL, longitude REAL, rating REAL, price_per_person INTEGER,
              open_hours_json TEXT, tags_json TEXT, cover_image TEXT, review_count INTEGER,
              queue_estimate_json TEXT, visit_duration INTEGER, high_freq_keywords_json TEXT,
              suitable_for_json TEXT, atmosphere_json TEXT, district TEXT, business_area TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE poi_feature_index (
              poi_id TEXT PRIMARY KEY, city TEXT, category TEXT, derived_category TEXT,
              district TEXT, business_area TEXT, price_band TEXT, queue_band TEXT,
              rating_score REAL, popularity_score REAL, static_score REAL,
              is_meal_candidate INTEGER, is_experience_candidate INTEGER,
              is_low_queue INTEGER, is_photo_friendly INTEGER, tags_text TEXT, keywords_text TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE ugc_evidence_index (
              poi_id TEXT, rank INTEGER, snippet TEXT, source TEXT, score REAL, tags_text TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO app_pois VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "hf_park",
                "杏花公园",
                "hefei",
                "restaurant",
                "公园",
                "庐阳区寿春路",
                31.87,
                117.27,
                4.6,
                None,
                "{}",
                json.dumps(["公园", "拍照"], ensure_ascii=False),
                None,
                900,
                json.dumps({"weekday_peak": 8, "weekend_peak": 12}),
                70,
                json.dumps([{"keyword": "拍照", "count": 65}], ensure_ascii=False),
                json.dumps(["friends"], ensure_ascii=False),
                json.dumps(["photogenic"], ensure_ascii=False),
                "庐阳区",
                "逍遥津",
            ),
        )
        conn.execute(
            "INSERT INTO poi_feature_index VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "hf_park",
                "hefei",
                "restaurant",
                "scenic",
                "庐阳区",
                "逍遥津",
                "free",
                "low",
                0.9,
                0.8,
                0.85,
                0,
                1,
                1,
                1,
                "公园 拍照",
                "带老人 出片",
            ),
        )
        conn.execute(
            "INSERT INTO ugc_evidence_index VALUES (?,?,?,?,?,?)",
            ("hf_park", 1, "适合带老人慢慢散步，也很出片。", "ugc", 4.8, "senior photo"),
        )

    pois = load_sqlite_pois(db_path, city="hefei")

    assert len(pois) == 1
    assert pois[0].category == "scenic"
    assert pois[0].highlight_quotes[0].category == "ugc_review"
    assert "带老人" in pois[0].highlight_quotes[0].quote


def test_health_exposes_unified_retrieval_subsystems():
    from fastapi.testclient import TestClient

    from app.main import app

    payload = TestClient(app).get("/health").json()

    assert {"rag", "faiss", "memory", "cache", "amap"} <= set(payload)
    assert {"enabled", "index_exists", "document_count"} <= set(payload["faiss"])


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


def test_route_validator_allows_non_food_route_when_meal_not_required():
    from app.schemas.plan import HardConstraints, RouteMetrics, RouteSkeleton, RouteStop, SoftPreferences, StructuredIntent
    from app.services.route_validator import RouteValidator

    scenic = _poi("hf_scenic", "scenic")
    route = RouteSkeleton(
        style="relaxed",
        stops=[
            RouteStop(poi_id="hf_scenic", arrival_time="14:00", departure_time="14:50", duration_min=50),
            RouteStop(poi_id="hf_scenic", arrival_time="15:00", departure_time="15:50", duration_min=50),
            RouteStop(poi_id="hf_scenic", arrival_time="16:00", departure_time="16:50", duration_min=50),
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
        hard_constraints=HardConstraints(
            start_time="14:00",
            end_time="18:00",
            must_include_meal=False,
            must_include_experience=True,
        ),
        soft_preferences=SoftPreferences(),
        must_visit_pois=[],
    )

    result = RouteValidator(repo=Repo([scenic])).validate(route, intent)

    assert result.is_valid is True

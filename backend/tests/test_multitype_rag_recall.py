import json
import sqlite3
from pathlib import Path

from app.schemas.plan import (
    HardConstraints,
    PlanContext,
    RouteMetrics,
    RouteSkeleton,
    RouteStop,
    SoftPreferences,
    StructuredIntent,
)
from app.schemas.pool import TimeWindow


def _write_multitype_sqlite(path: Path) -> None:
    con = sqlite3.connect(path)
    con.execute(
        """
        create table app_pois (
            id text primary key,
            name text,
            city text,
            category text,
            sub_category text,
            address text,
            latitude real,
            longitude real,
            rating real,
            price_per_person integer,
            open_hours_json text,
            tags_json text,
            cover_image text,
            review_count integer,
            queue_estimate_json text,
            visit_duration integer,
            high_freq_keywords_json text,
            suitable_for_json text,
            atmosphere_json text,
            district text,
            business_area text
        )
        """
    )
    con.execute(
        """
        create table poi_feature_index (
            poi_id text primary key,
            city text,
            category text,
            derived_category text,
            district text,
            business_area text,
            price_band text,
            queue_band text,
            rating_score real,
            popularity_score real,
            static_score real,
            is_meal_candidate integer,
            is_experience_candidate integer,
            is_low_queue integer,
            is_photo_friendly integer,
            tags_text text,
            keywords_text text
        )
        """
    )
    con.execute(
        """
        create table ugc_evidence_index (
            poi_id text,
            rank integer,
            snippet text,
            source text,
            score real,
            tags_text text
        )
        """
    )
    rows = [
        (
            "hf_food",
            "庐州徽菜馆",
            "hefei",
            "restaurant",
            "安徽菜(徽菜)",
            "包河区徽州大道 1 号",
            31.82,
            117.29,
            4.7,
            88,
            "{}",
            ["餐饮", "安徽菜(徽菜)", "低排队"],
            320,
            {"weekday_peak": 12, "weekend_peak": 18},
            55,
            [{"keyword": "徽菜", "count": 90}],
            ["friends", "foodie"],
            ["lively"],
            "包河区",
            "滨湖",
        ),
        (
            "hf_scenic",
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
            ["景点", "公园", "拍照", "安静"],
            900,
            {"weekday_peak": 8, "weekend_peak": 12},
            70,
            [{"keyword": "公园", "count": 88}, {"keyword": "拍照", "count": 65}],
            ["friends", "couple", "senior"],
            ["relaxed", "photogenic"],
            "庐阳区",
            "逍遥津",
        ),
    ]
    con.executemany(
        """
        insert into app_pois values (
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
        )
        """,
        [
            (
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
                row[5],
                row[6],
                row[7],
                row[8],
                row[9],
                row[10],
                json.dumps(row[11], ensure_ascii=False),
                None,
                row[12],
                json.dumps(row[13], ensure_ascii=False),
                row[14],
                json.dumps(row[15], ensure_ascii=False),
                json.dumps(row[16], ensure_ascii=False),
                json.dumps(row[17], ensure_ascii=False),
                row[18],
                row[19],
            )
            for row in rows
        ],
    )
    con.executemany(
        """
        insert into poi_feature_index values (
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
        )
        """,
        [
            (
                "hf_food",
                "hefei",
                "restaurant",
                "restaurant",
                "包河区",
                "滨湖",
                "mid",
                "low",
                0.94,
                0.2,
                0.7,
                1,
                0,
                1,
                0,
                "安徽菜 低排队 friends foodie",
                "徽菜 包河区",
            ),
            (
                "hf_scenic",
                "hefei",
                "restaurant",
                "scenic",
                "庐阳区",
                "逍遥津",
                "free",
                "low",
                0.92,
                0.7,
                0.8,
                0,
                1,
                1,
                1,
                "公园 景点 安静 拍照 senior relaxed photogenic",
                "公园 拍照 带老人",
            ),
        ],
    )
    con.executemany(
        "insert into ugc_evidence_index values (?,?,?,?,?,?)",
        [
            ("hf_scenic", 1, "适合带老人慢慢散步，路面平缓，树荫多。", "ugc", 4.9, "senior quiet"),
            ("hf_scenic", 2, "傍晚拍照很出片，也适合安静走走。", "ugc", 4.8, "photo quiet"),
            ("hf_food", 1, "徽菜味道稳定，高峰期排队不算久。", "ugc", 4.7, "food low_queue"),
        ],
    )
    con.commit()
    con.close()


def test_sqlite_loader_uses_derived_category_and_merges_ugc_evidence(tmp_path):
    from app.repositories.poi_repo import PoiRepository

    db_path = tmp_path / "hefei_pois.sqlite"
    _write_multitype_sqlite(db_path)

    repo = PoiRepository(sqlite_path=db_path)
    pois = repo.list_by_city("hefei")
    by_id = {poi.id: poi for poi in pois}

    assert by_id["hf_scenic"].category == "scenic"
    assert by_id["hf_scenic"].latitude == 31.87
    assert by_id["hf_scenic"].longitude == 117.27
    assert [quote.source for quote in by_id["hf_scenic"].highlight_quotes[:2]] == ["ugc", "ugc"]
    assert "带老人" in by_id["hf_scenic"].highlight_quotes[0].quote


def test_rag_index_builds_poi_profile_and_ugc_review_documents(tmp_path):
    from app.repositories.poi_repo import PoiRepository
    from app.repositories.rag_index import build_poi_document, build_ugc_documents

    db_path = tmp_path / "hefei_pois.sqlite"
    _write_multitype_sqlite(db_path)
    scenic = PoiRepository(sqlite_path=db_path).get("hf_scenic")

    profile = build_poi_document(scenic)
    reviews = build_ugc_documents(scenic)

    assert profile.metadata["source_type"] == "poi_profile"
    assert profile.metadata["category"] == "scenic"
    assert profile.metadata["district"] == "庐阳区"
    assert len(reviews) == 2
    assert reviews[0].doc_id == "ugc_review:hf_scenic:0"
    assert reviews[0].metadata["source_type"] == "ugc_review"
    assert "带老人" in reviews[0].text


class FakeVectorIndex:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def query(self, *, text, city, top_k, category_filters=None, source_types=None):
        self.calls.append(
            {
                "text": text,
                "city": city,
                "top_k": top_k,
                "category_filters": category_filters,
                "source_types": source_types,
            }
        )
        allowed_sources = set(source_types or [])
        results = []
        for row in self.rows:
            metadata = row.get("metadata", {})
            if metadata.get("city") != city:
                continue
            if category_filters and metadata.get("category") not in category_filters:
                continue
            if allowed_sources and row.get("source_type") not in allowed_sources:
                continue
            results.append(row)
        return results[:top_k]


def test_retrieval_aggregates_multiple_sources_per_poi(tmp_path):
    from app.repositories.poi_repo import PoiRepository
    from app.schemas.rag import RetrievalQuery
    from app.services.retrieval_service import RetrievalService

    db_path = tmp_path / "hefei_pois.sqlite"
    _write_multitype_sqlite(db_path)
    fake_index = FakeVectorIndex(
        [
            {
                "poi_id": "hf_scenic",
                "score": 0.72,
                "doc_id": "poi_profile:hf_scenic",
                "source_type": "poi_profile",
                "text": "杏花公园 景点 公园 拍照",
                "metadata": {"city": "hefei", "category": "scenic"},
            },
            {
                "poi_id": "hf_scenic",
                "score": 0.96,
                "doc_id": "ugc_review:hf_scenic:0",
                "source_type": "ugc_review",
                "text": "适合带老人慢慢散步，路面平缓。",
                "metadata": {"city": "hefei", "category": "scenic"},
            },
        ]
    )

    results = RetrievalService(
        repo=PoiRepository(sqlite_path=db_path),
        vector_index=fake_index,
    ).retrieve(
        RetrievalQuery(
            city="hefei",
            text="适合带老人散步的公园",
            top_k=3,
            source_types=["poi_profile", "ugc_review"],
        )
    )

    assert [item.poi_id for item in results] == ["hf_scenic"]
    assert results[0].score == 0.96
    assert results[0].provenance == ["semantic_poi_profile", "semantic_ugc_review"]
    assert [snippet.source_type for snippet in results[0].evidence_snippets] == [
        "ugc_review",
        "poi_profile",
    ]


def test_route_validator_allows_non_food_route_when_meal_not_required(tmp_path):
    from app.repositories.poi_repo import PoiRepository
    from app.services.route_validator import RouteValidator

    db_path = tmp_path / "hefei_pois.sqlite"
    _write_multitype_sqlite(db_path)
    repo = PoiRepository(sqlite_path=db_path)
    route = RouteSkeleton(
        style="relaxed",
        stops=[
            RouteStop(poi_id="hf_scenic", arrival_time="14:00", departure_time="15:10", duration_min=70),
            RouteStop(poi_id="hf_scenic", arrival_time="15:20", departure_time="16:30", duration_min=70),
            RouteStop(poi_id="hf_scenic", arrival_time="16:40", departure_time="17:50", duration_min=70),
        ],
        dropped_poi_ids=[],
        drop_reasons={},
        metrics=RouteMetrics(
            total_duration_min=230,
            total_cost=0,
            poi_count=3,
            walking_distance_meters=0,
            queue_total_min=36,
        ),
    )
    intent = StructuredIntent(
        hard_constraints=HardConstraints(
            start_time="14:00",
            end_time="18:00",
            must_include_meal=False,
            must_include_experience=True,
        ),
        soft_preferences=SoftPreferences(custom_notes=["只想公园散步，不吃饭"]),
        must_visit_pois=[],
    )

    result = RouteValidator(repo=repo).validate(
        route,
        intent,
        context=PlanContext(
            city="hefei",
            date="2026-05-02",
            time_window=TimeWindow(start="14:00", end="18:00"),
            party="friends",
        ),
    )

    assert result.is_valid is True
    assert all(issue.severity == "warning" for issue in result.issues)


def test_route_validator_requires_meal_when_intent_requires_it(tmp_path):
    from app.repositories.poi_repo import PoiRepository
    from app.services.route_validator import RouteValidator

    db_path = tmp_path / "hefei_pois.sqlite"
    _write_multitype_sqlite(db_path)
    route = RouteSkeleton(
        style="relaxed",
        stops=[
            RouteStop(poi_id="hf_scenic", arrival_time="14:00", departure_time="15:10", duration_min=70),
            RouteStop(poi_id="hf_scenic", arrival_time="15:20", departure_time="16:30", duration_min=70),
            RouteStop(poi_id="hf_scenic", arrival_time="16:40", departure_time="17:50", duration_min=70),
        ],
        dropped_poi_ids=[],
        drop_reasons={},
        metrics=RouteMetrics(
            total_duration_min=230,
            total_cost=0,
            poi_count=3,
            walking_distance_meters=0,
            queue_total_min=36,
        ),
    )
    intent = StructuredIntent(
        hard_constraints=HardConstraints(
            start_time="14:00",
            end_time="18:00",
            must_include_meal=True,
            must_include_experience=True,
        ),
        soft_preferences=SoftPreferences(custom_notes=["先逛公园再吃饭"]),
        must_visit_pois=[],
    )

    result = RouteValidator(repo=PoiRepository(sqlite_path=db_path)).validate(route, intent)

    assert result.is_valid is False
    assert "meal_missing" in {issue.code for issue in result.issues}


class FakeRetrievalService:
    def __init__(self):
        self.calls = []

    def retrieve(self, query):
        from app.schemas.rag import EvidenceSnippet, RetrievedPoi

        self.calls.append(query)
        if query.source_types == ["poi_profile"]:
            return [
                RetrievedPoi(
                    poi_id="hf_food",
                    score=0.88,
                    evidence_snippets=[
                        EvidenceSnippet(
                            doc_id="poi_profile:hf_food",
                            source_type="poi_profile",
                            text="庐州徽菜馆 低排队 徽菜",
                            score=0.88,
                        )
                    ],
                    provenance=["semantic_poi_profile"],
                )
            ]
        if query.source_types == ["ugc_review"]:
            return [
                RetrievedPoi(
                    poi_id="hf_scenic",
                    score=0.96,
                    evidence_snippets=[
                        EvidenceSnippet(
                            doc_id="ugc_review:hf_scenic:0",
                            source_type="ugc_review",
                            text="适合带老人慢慢散步，路面平缓。",
                            score=0.96,
                        )
                    ],
                    provenance=["semantic_ugc_review"],
                )
            ]
        return []


def test_pool_recall_uses_profile_and_ugc_channels(tmp_path):
    from app.repositories.poi_repo import PoiRepository
    from app.schemas.pool import PoolRequest
    from app.services.pool_service import PoolService

    db_path = tmp_path / "hefei_pois.sqlite"
    _write_multitype_sqlite(db_path)
    retrieval = FakeRetrievalService()

    pool = PoolService(repo=PoiRepository(sqlite_path=db_path), retrieval_service=retrieval).generate_pool(
        PoolRequest(
            user_id="mock_user",
            city="hefei",
            free_text="想吃徽菜，也想找适合带老人散步的公园",
            budget_per_person=120,
        )
    )

    source_type_calls = [call.source_types for call in retrieval.calls]
    assert ["poi_profile"] in source_type_calls
    assert ["ugc_review"] in source_type_calls
    pooled = [poi for category in pool.categories for poi in category.pois]
    assert {"hf_food", "hf_scenic"} <= {poi.id for poi in pooled}
    assert any("semantic_ugc_review" in poi.retrieval_provenance for poi in pooled)


def test_intent_service_does_not_require_meal_for_explicit_non_food_query():
    from app.schemas.plan import PlanContext
    from app.services.intent_service import IntentService

    intent = IntentService().parse_intent(
        "mock_user",
        [],
        "只想公园散步拍照，不吃饭",
        PlanContext(
            city="hefei",
            date="2026-05-02",
            time_window=TimeWindow(start="14:00", end="18:00"),
            party="friends",
        ),
    )

    assert intent.hard_constraints.must_include_meal is False
    assert intent.hard_constraints.must_include_experience is True

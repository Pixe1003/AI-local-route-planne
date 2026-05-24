import json
import sqlite3
from pathlib import Path

from app.schemas.plan import PlanContext, PlanRequest
from app.schemas.pool import PoolRequest, TimeWindow


def _write_sqlite_pois(path: Path) -> None:
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
    rows = [
        (
            "hf_poi_food",
            "包河庐州徽菜馆",
            "hefei",
            "restaurant",
            "安徽菜(徽菜)",
            "包河区徽州大道 1 号",
            31.82,
            117.29,
            4.7,
            88,
            "{}",
            ["hefei", "餐饮", "安徽菜(徽菜)", "包河区", "低排队"],
            320,
            {"weekday_peak": 12, "weekend_peak": 18},
            [{"keyword": "徽菜", "count": 90}, {"keyword": "包河区", "count": 72}],
            ["friends", "foodie"],
            ["lively"],
            "包河区",
            "滨湖",
        ),
        (
            "hf_poi_cafe",
            "包河湖畔咖啡",
            "hefei",
            "restaurant",
            "咖啡厅",
            "包河区湖畔路 8 号",
            31.83,
            117.3,
            4.5,
            42,
            "{}",
            ["hefei", "咖啡", "休息", "包河区", "低排队"],
            180,
            {"weekday_peak": 8, "weekend_peak": 15},
            [{"keyword": "咖啡", "count": 80}, {"keyword": "休息", "count": 60}],
            ["friends", "couple"],
            ["relaxed", "photogenic"],
            "包河区",
            "滨湖",
        ),
        (
            "hf_poi_tea",
            "庐阳茶艺馆",
            "hefei",
            "restaurant",
            "茶艺馆",
            "庐阳区长江路 9 号",
            31.87,
            117.26,
            4.6,
            58,
            "{}",
            ["hefei", "茶艺", "文艺", "雨天友好", "庐阳区"],
            210,
            {"weekday_peak": 10, "weekend_peak": 22},
            [{"keyword": "茶艺", "count": 81}, {"keyword": "文艺", "count": 50}],
            ["friends", "couple"],
            ["relaxed", "literary"],
            "庐阳区",
            "三孝口",
        ),
        (
            "hf_poi_hotpot",
            "蜀山火锅局",
            "hefei",
            "restaurant",
            "火锅店",
            "蜀山区黄山路 6 号",
            31.85,
            117.22,
            4.3,
            120,
            "{}",
            ["hefei", "火锅", "朋友聚会", "蜀山区"],
            150,
            {"weekday_peak": 20, "weekend_peak": 35},
            [{"keyword": "火锅", "count": 80}],
            ["friends", "foodie"],
            ["lively"],
            "蜀山区",
            "大蜀山",
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
                55,
                json.dumps(row[14], ensure_ascii=False),
                json.dumps(row[15], ensure_ascii=False),
                json.dumps(row[16], ensure_ascii=False),
                row[17],
                row[18],
            )
            for row in rows
        ],
    )
    con.commit()
    con.close()


class FakeVectorIndex:
    def __init__(self, rows):
        self.rows = rows

    def query(self, *, text, city, top_k, category_filters=None):
        del text
        results = []
        for row in self.rows:
            if category_filters and row["category"] not in category_filters:
                continue
            if row["metadata"].get("city") != city:
                continue
            results.append(row)
        return results[:top_k]


def test_sqlite_repository_maps_real_poi_fields_and_categories(tmp_path):
    from app.repositories.poi_repo import PoiRepository
    from app.repositories.rag_index import build_poi_document

    db_path = tmp_path / "hefei_pois.sqlite"
    _write_sqlite_pois(db_path)

    repo = PoiRepository(sqlite_path=db_path)
    pois = repo.list_by_city("hefei")
    by_id = {poi.id: poi for poi in pois}

    assert by_id["hf_poi_food"].category == "restaurant"
    assert by_id["hf_poi_cafe"].category == "cafe"
    assert by_id["hf_poi_tea"].category == "culture"
    assert by_id["hf_poi_food"].highlight_quotes[0].source == "poi_profile"

    document = build_poi_document(by_id["hf_poi_food"])
    assert document.doc_id == "poi_profile:hf_poi_food"
    assert "包河区" in document.text
    assert "徽菜" in document.text
    assert document.metadata["city"] == "hefei"


def test_retrieval_service_returns_evidence_and_provenance(tmp_path):
    from app.repositories.poi_repo import PoiRepository
    from app.schemas.rag import RetrievalQuery
    from app.services.retrieval_service import RetrievalService

    db_path = tmp_path / "hefei_pois.sqlite"
    _write_sqlite_pois(db_path)
    repo = PoiRepository(sqlite_path=db_path)
    fake_index = FakeVectorIndex(
        [
            {
                "poi_id": "hf_poi_food",
                "score": 0.91,
                "doc_id": "poi_profile:hf_poi_food",
                "source_type": "poi_profile",
                "text": "包河庐州徽菜馆 位于包河区 高频关键词：徽菜、包河区",
                "metadata": {"city": "hefei", "category": "restaurant"},
            }
        ]
    )

    results = RetrievalService(repo=repo, vector_index=fake_index).retrieve(
        RetrievalQuery(city="hefei", text="包河区徽菜少排队", top_k=5)
    )

    assert [item.poi_id for item in results] == ["hf_poi_food"]
    assert results[0].score == 0.91
    assert results[0].provenance == ["semantic_poi_profile"]
    assert results[0].evidence_snippets[0].source_type == "poi_profile"
    assert "徽菜" in results[0].evidence_snippets[0].text


def test_pool_plan_and_replan_reuse_rag_evidence_for_hefei(tmp_path):
    from app.repositories.poi_repo import PoiRepository
    from app.services.plan_service import PlanService
    from app.services.pool_service import PoolService
    from app.services.retrieval_service import RetrievalService
    from app.services.route_replanner import ReplanEvent, RouteReplanner
    from app.services.solver_service import SolverService

    db_path = tmp_path / "hefei_pois.sqlite"
    _write_sqlite_pois(db_path)
    repo = PoiRepository(sqlite_path=db_path)
    fake_index = FakeVectorIndex(
        [
            {
                "poi_id": "hf_poi_food",
                "score": 0.95,
                "doc_id": "poi_profile:hf_poi_food",
                "source_type": "poi_profile",
                "text": "包河庐州徽菜馆 位于包河区，低排队，关键词：徽菜",
                "metadata": {"city": "hefei", "category": "restaurant"},
            },
            {
                "poi_id": "hf_poi_tea",
                "score": 0.88,
                "doc_id": "poi_profile:hf_poi_tea",
                "source_type": "poi_profile",
                "text": "庐阳茶艺馆 茶艺 文艺 雨天友好",
                "metadata": {"city": "hefei", "category": "culture"},
            },
            {
                "poi_id": "hf_poi_cafe",
                "score": 0.82,
                "doc_id": "poi_profile:hf_poi_cafe",
                "source_type": "poi_profile",
                "text": "包河湖畔咖啡 低排队 适合休息",
                "metadata": {"city": "hefei", "category": "cafe"},
            },
            {
                "poi_id": "hf_poi_hotpot",
                "score": 0.6,
                "doc_id": "poi_profile:hf_poi_hotpot",
                "source_type": "poi_profile",
                "text": "蜀山火锅局 朋友聚会",
                "metadata": {"city": "hefei", "category": "restaurant"},
            },
        ]
    )
    retrieval = RetrievalService(repo=repo, vector_index=fake_index)

    pool = PoolService(repo=repo, retrieval_service=retrieval).generate_pool(
        PoolRequest(
            user_id="mock_user",
            city="hefei",
            date="2026-05-02",
            time_window=TimeWindow(start="14:00", end="20:00"),
            persona_tags=["foodie", "literary"],
            party="friends",
            budget_per_person=300,
            free_text="包河区徽菜，少排队，也想有文艺休息点",
        )
    )
    pooled = [poi for category in pool.categories for poi in category.pois]

    assert {poi.id for poi in pooled} >= {"hf_poi_food", "hf_poi_tea", "hf_poi_cafe"}
    assert any(poi.retrieval_provenance for poi in pooled)
    assert any(poi.evidence_snippets for poi in pooled)

    plan_service = PlanService(
        repo=repo,
        retrieval_service=retrieval,
        solver=SolverService(repo=repo),
    )
    plan = plan_service.generate_plans(
        PlanRequest(
            pool_id=pool.pool_id,
            selected_poi_ids=pool.default_selected_ids,
            free_text="包河区徽菜，少排队，也想有文艺休息点",
            context=PlanContext(
                city="hefei",
                date="2026-05-02",
                time_window=TimeWindow(start="14:00", end="20:00"),
                party="friends",
                budget_per_person=300,
            ),
        )
    ).plans[0]

    assert plan.summary.validation.is_valid is True
    assert plan.alternative_pois
    assert any(candidate.retrieval_provenance for candidate in plan.alternative_pois)

    replan = RouteReplanner(repo=repo, retrieval_service=retrieval).replan(
        plan,
        ReplanEvent(event_type="USER_REJECT_POI", message="少排队，换一个低排队点"),
    )

    assert replan.plan.summary.validation.is_valid is True
    assert replan.plan.stops


def test_retrieval_fallback_returns_no_results_when_index_unavailable(tmp_path):
    from app.repositories.poi_repo import PoiRepository
    from app.schemas.rag import RetrievalQuery
    from app.services.retrieval_service import RetrievalService

    db_path = tmp_path / "hefei_pois.sqlite"
    _write_sqlite_pois(db_path)

    results = RetrievalService(repo=PoiRepository(sqlite_path=db_path), vector_index=None).retrieve(
        RetrievalQuery(city="hefei", text="徽菜", top_k=5)
    )

    assert results == []

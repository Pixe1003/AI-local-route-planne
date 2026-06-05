import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.ugc_vector_repo import UgcVectorRepo
from app.schemas.plan import PlanContext
from app.schemas.pool import TimeWindow
from app.services.pool_service import PoolService
from scripts.build_retrieval_index import build_retrieval_index
from scripts.generate_demo_ugc import generate_demo_ugc


def test_generated_demo_ugc_loads_and_populates_retrieval_index(tmp_path: Path) -> None:
    db_path = tmp_path / "hefei_pois.sqlite"
    _write_demo_poi_db(db_path)
    ugc_path = tmp_path / "ugc_hefei.jsonl"

    stats = generate_demo_ugc(
        sqlite_path=db_path,
        out_path=ugc_path,
        category_limits={"restaurant": 1, "cafe": 1, "culture": 1},
    )

    assert stats["rows"] == 3
    reviews = UgcVectorRepo(ugc_path).list_reviews(city="hefei")
    assert len(reviews) == 6
    assert {review.source for review in reviews} == {"simulated_ugc"}

    index_stats = build_retrieval_index(
        main_db_path=db_path,
        source_db_paths=[db_path],
        ugc_path=ugc_path,
    )
    assert index_stats["ugc_evidence_rows"] > 0
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ugc_evidence_index").fetchone()[0] > 0


def test_weather_adjustment_prefers_indoor_pois_for_rainy_demo_context() -> None:
    service = PoolService.__new__(PoolService)
    rainy_context = PlanContext(
        city="hefei",
        date="2026-06-03",
        time_window=TimeWindow(start="14:00", end="20:00"),
        weather_condition="rainy",
    )
    culture = SimpleNamespace(category="culture", latitude=31.82, longitude=117.22)
    outdoor = SimpleNamespace(category="outdoor", latitude=31.82, longitude=117.22)

    assert service._weather_adjustment_score(culture, rainy_context) > 0
    assert service._weather_adjustment_score(outdoor, rainy_context) < 0


def test_agent_run_returns_text_route_when_amap_key_is_missing() -> None:
    response = TestClient(app).post(
        "/api/agent/run",
        json={
            "user_id": "business_eval_user",
            "free_text": "今天下午想少排队、吃本地菜、顺路拍照",
            "city": "hefei",
            "date": "2026-06-03",
            "time_window": {"start": "14:00", "end": "20:00"},
            "budget_per_person": 180,
            "weather_condition": "normal",
            "origin_latitude": 31.8206,
            "origin_longitude": 117.2272,
            "radius_meters": 8000,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["route_chain"] is None
    assert payload["ordered_poi_ids"]
    assert payload["transport_notice"]
    assert "文字路线建议" in payload["transport_notice"]


def _write_demo_poi_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE app_pois (
              id TEXT PRIMARY KEY,
              name TEXT,
              city TEXT,
              category TEXT,
              sub_category TEXT,
              address TEXT,
              latitude REAL,
              longitude REAL,
              rating REAL,
              price_per_person INTEGER,
              open_hours_json TEXT,
              tags_json TEXT,
              cover_image TEXT,
              review_count INTEGER,
              queue_estimate_json TEXT,
              visit_duration INTEGER,
              high_freq_keywords_json TEXT,
              suitable_for_json TEXT,
              atmosphere_json TEXT,
              district TEXT,
              business_area TEXT
            )
            """
        )
        rows = [
            ("hf_food", "庐州小馆", "restaurant", "徽菜", 4.8, 42, 18, "包河区"),
            ("hf_cafe", "湖畔咖啡", "cafe", "咖啡", 4.7, 38, 12, "蜀山区"),
            ("hf_museum", "合肥小展馆", "culture", "展览", 4.6, 0, 10, "庐阳区"),
        ]
        for poi_id, name, category, sub_category, rating, price, queue, district in rows:
            conn.execute(
                """
                INSERT INTO app_pois (
                  id, name, city, category, sub_category, address, latitude, longitude,
                  rating, price_per_person, open_hours_json, tags_json, cover_image,
                  review_count, queue_estimate_json, visit_duration,
                  high_freq_keywords_json, suitable_for_json, atmosphere_json,
                  district, business_area
                ) VALUES (?, ?, 'hefei', ?, ?, '合肥测试地址', 31.82, 117.22,
                          ?, ?, '{}', ?, NULL, 120, ?, 50, ?, '[]', '[]', ?, ?)
                """,
                (
                    poi_id,
                    name,
                    category,
                    sub_category,
                    rating,
                    price,
                    json.dumps([sub_category, district], ensure_ascii=False),
                    json.dumps({"weekend_peak": queue}, ensure_ascii=False),
                    json.dumps([{"keyword": sub_category, "count": 20}], ensure_ascii=False),
                    district,
                    district,
                ),
            )
        conn.commit()

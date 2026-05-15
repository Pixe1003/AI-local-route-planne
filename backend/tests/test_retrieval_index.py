from __future__ import annotations

import importlib.util
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.schemas.pool import PoolRequest
from app.schemas.preferences import PreferenceSnapshot
from app.services.poi_retrieval_service import PoiRetrievalService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "build_retrieval_index.py"


spec = importlib.util.spec_from_file_location("build_retrieval_index", SCRIPT_PATH)
build_module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(build_module)


@dataclass
class FakePoi:
    id: str
    city: str = "hefei"


class FakeRepo:
    def __init__(self, poi_ids: list[str]) -> None:
        self._pois = {poi_id: FakePoi(id=poi_id) for poi_id in poi_ids}

    def get_many(self, poi_ids):
        return [self._pois[poi_id] for poi_id in poi_ids if poi_id in self._pois]

    def list_by_city(self, city: str):
        return [poi for poi in self._pois.values() if poi.city == city]


def test_build_retrieval_index_creates_repeatable_derived_tables(tmp_path: Path) -> None:
    main_db = tmp_path / "main.sqlite"
    scenic_db = tmp_path / "scenic.sqlite"
    shopping_db = tmp_path / "shopping.sqlite"
    ugc_path = tmp_path / "ugc.jsonl"

    _create_app_pois(main_db, [_poi("food_1", "小巷本地菜", "restaurant", tags=["本地菜", "少排队"])])
    _create_app_pois(scenic_db, [_poi("scenic_1", "河岸拍照公园", "scenic", price=0, tags=["拍照", "散步"])])
    _create_app_pois(shopping_db, [_poi("shop_1", "中心商场", "shopping", tags=["商场", "购物"])])
    ugc_path.write_text(
        json.dumps(
            {
                "poi_id": "food_1",
                "reviews": [{"content": "本地菜味道稳定，排队时间短。", "rating": 4.8}],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    stats = build_module.build_retrieval_index(
        main_db_path=main_db,
        source_db_paths=[main_db, scenic_db, shopping_db],
        ugc_path=ugc_path,
    )
    stats_after_rerun = build_module.build_retrieval_index(
        main_db_path=main_db,
        source_db_paths=[main_db, scenic_db, shopping_db],
        ugc_path=ugc_path,
    )

    assert stats["pois"] == 3
    assert stats_after_rerun["pois"] == 3
    with sqlite3.connect(main_db) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')"
            ).fetchall()
        }
        assert {"poi_feature_index", "poi_retrieval_fts", "poi_bucket_top", "ugc_evidence_index"} <= tables
        categories = {
            row[0]
            for row in conn.execute("SELECT DISTINCT category FROM poi_feature_index").fetchall()
        }
        assert {"restaurant", "scenic", "shopping"} <= categories
        assert conn.execute("SELECT COUNT(*) FROM app_pois").fetchone()[0] == 1
        assert _fts_ids(conn, "拍照") == ["scenic_1"]
        assert _fts_ids(conn, "本地菜") == ["food_1"]
        assert _fts_ids(conn, "商场") == ["shop_1"]


def test_poi_retrieval_service_uses_liked_bucket_fts_and_supplements(tmp_path: Path) -> None:
    main_db = tmp_path / "main.sqlite"
    ugc_path = tmp_path / "ugc.jsonl"
    rows = [
        _poi("food_low_queue", "本地菜小馆", "restaurant", price=70, queue=8, tags=["本地菜", "少排队"]),
        _poi("food_high_queue", "热门排队餐厅", "restaurant", price=90, queue=70, rating=4.0, tags=["本地菜"]),
        _poi("photo_spot", "湖边拍照步道", "scenic", price=0, queue=0, tags=["拍照", "散步"]),
        _poi("mall_1", "银泰商场", "shopping", price=60, queue=10, tags=["商场", "购物"]),
    ]
    _create_app_pois(main_db, rows)
    ugc_path.write_text("", encoding="utf-8")
    build_module.build_retrieval_index(
        main_db_path=main_db,
        source_db_paths=[main_db],
        ugc_path=ugc_path,
    )

    service = PoiRetrievalService(db_path=main_db, repo=FakeRepo([row["id"] for row in rows]))
    result = service.retrieve_with_stats(
        PoolRequest(
            user_id="u1",
            city="hefei",
            free_text="想拍照散步，再吃本地菜，少排队，顺便逛商场",
            budget_per_person=80,
            preference_snapshot=PreferenceSnapshot(user_id="u1", liked_poi_ids=["mall_1"]),
        ),
        limit=10,
    )

    assert result.poi_ids[0] == "mall_1"
    assert {"food_low_queue", "photo_spot", "mall_1"} <= set(result.poi_ids)
    assert result.poi_ids.index("food_low_queue") < result.poi_ids.index("food_high_queue")
    assert result.stats["total_candidates"] <= 10


def _fts_ids(conn: sqlite3.Connection, query: str) -> list[str]:
    return [
        row[0]
        for row in conn.execute(
            "SELECT poi_id FROM poi_retrieval_fts WHERE poi_retrieval_fts MATCH ? ORDER BY poi_id",
            (query,),
        ).fetchall()
    ]


def _create_app_pois(db_path: Path, rows: list[dict]) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE app_pois (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              city TEXT NOT NULL,
              category TEXT NOT NULL,
              sub_category TEXT,
              address TEXT,
              latitude REAL,
              longitude REAL,
              rating REAL,
              price_per_person INTEGER,
              tags_json TEXT,
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
        conn.executemany(
            """
            INSERT INTO app_pois (
              id, name, city, category, sub_category, address, latitude, longitude,
              rating, price_per_person, tags_json, review_count, queue_estimate_json,
              visit_duration, high_freq_keywords_json, suitable_for_json, atmosphere_json,
              district, business_area
            ) VALUES (
              :id, :name, :city, :category, :sub_category, :address, :latitude, :longitude,
              :rating, :price_per_person, :tags_json, :review_count, :queue_estimate_json,
              :visit_duration, :high_freq_keywords_json, :suitable_for_json, :atmosphere_json,
              :district, :business_area
            )
            """,
            rows,
        )
        conn.commit()


def _poi(
    poi_id: str,
    name: str,
    category: str,
    *,
    price: int = 80,
    queue: int = 15,
    rating: float = 4.8,
    tags: list[str] | None = None,
) -> dict:
    tags = tags or []
    return {
        "id": poi_id,
        "name": name,
        "city": "hefei",
        "category": category,
        "sub_category": category,
        "address": "合肥",
        "latitude": 31.82,
        "longitude": 117.22,
        "rating": rating,
        "price_per_person": price,
        "tags_json": json.dumps(tags, ensure_ascii=False),
        "review_count": 100,
        "queue_estimate_json": json.dumps({"weekday_peak": queue, "weekend_peak": queue}),
        "visit_duration": 50,
        "high_freq_keywords_json": json.dumps([{"keyword": tag, "count": 10} for tag in tags], ensure_ascii=False),
        "suitable_for_json": json.dumps(["couple"], ensure_ascii=False),
        "atmosphere_json": json.dumps(tags, ensure_ascii=False),
        "district": "蜀山区",
        "business_area": "测试商圈",
    }

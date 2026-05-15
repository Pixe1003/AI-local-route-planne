from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "processed"
DEFAULT_MAIN_DB = DATA_DIR / "hefei_pois.sqlite"
DEFAULT_SOURCE_DBS = [
    DATA_DIR / "hefei_pois.sqlite",
    DATA_DIR / "hefei_scenic_pois.sqlite",
    DATA_DIR / "hefei_shopping_pois.sqlite",
]
DEFAULT_UGC_PATH = DATA_DIR / "ugc_hefei.jsonl"

EXPERIENCE_CATEGORIES = {"culture", "scenic", "entertainment", "nightlife"}
DERIVED_TABLES = [
    "poi_feature_index",
    "poi_retrieval_fts",
    "poi_bucket_top",
    "ugc_evidence_index",
]


def build_retrieval_index(
    *,
    main_db_path: Path = DEFAULT_MAIN_DB,
    source_db_paths: Iterable[Path] = DEFAULT_SOURCE_DBS,
    ugc_path: Path = DEFAULT_UGC_PATH,
) -> dict[str, int]:
    pois = _load_pois(source_db_paths)
    evidence_by_poi, summaries_by_poi = _load_ugc_evidence(ugc_path)
    feature_rows = [_feature_row(poi, summaries_by_poi.get(poi["id"], "")) for poi in pois]
    bucket_rows = _bucket_rows(feature_rows)

    with sqlite3.connect(main_db_path) as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        _drop_derived_tables(conn)
        _create_derived_tables(conn)
        conn.executemany(
            """
            INSERT INTO poi_feature_index (
              poi_id, city, category, derived_category, district, business_area,
              price_band, queue_band, rating_score, popularity_score,
              static_score, is_meal_candidate, is_experience_candidate,
              is_low_queue, is_photo_friendly, tags_text, keywords_text
            ) VALUES (
              :poi_id, :city, :category, :derived_category, :district, :business_area,
              :price_band, :queue_band, :rating_score, :popularity_score,
              :static_score, :is_meal_candidate, :is_experience_candidate,
              :is_low_queue, :is_photo_friendly, :tags_text, :keywords_text
            )
            """,
            feature_rows,
        )
        conn.executemany(
            """
            INSERT INTO poi_retrieval_fts (
              poi_id, name, category, district, search_text
            ) VALUES (
              :poi_id, :name, :category, :district, :search_text
            )
            """,
            [
                {
                    "poi_id": row["poi_id"],
                    "name": row["name"],
                    "category": row["category"],
                    "district": row["district"],
                    "search_text": row["search_text"],
                }
                for row in feature_rows
            ],
        )
        conn.executemany(
            """
            INSERT INTO poi_bucket_top (
              scenario_key, poi_id, city, rank, score
            ) VALUES (
              :scenario_key, :poi_id, :city, :rank, :score
            )
            """,
            bucket_rows,
        )
        conn.executemany(
            """
            INSERT INTO ugc_evidence_index (
              poi_id, rank, snippet, source, score, tags_text
            ) VALUES (
              :poi_id, :rank, :snippet, :source, :score, :tags_text
            )
            """,
            evidence_by_poi,
        )
        conn.commit()

    return {
        "pois": len(feature_rows),
        "bucket_rows": len(bucket_rows),
        "ugc_evidence_rows": len(evidence_by_poi),
    }


def _load_pois(source_db_paths: Iterable[Path]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    pois: list[dict[str, Any]] = []
    for db_path in source_db_paths:
        if not db_path.exists():
            continue
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT
                  id, name, city, category, sub_category, address,
                  latitude, longitude, rating, price_per_person,
                  tags_json, review_count, queue_estimate_json,
                  visit_duration, high_freq_keywords_json,
                  suitable_for_json, atmosphere_json, district, business_area
                FROM app_pois
                """
            ).fetchall()
        for row in rows:
            poi_id = str(row["id"])
            if poi_id in seen:
                continue
            seen.add(poi_id)
            pois.append(dict(row))
    return pois


def _load_ugc_evidence(ugc_path: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if not ugc_path.exists():
        return [], {}

    with ugc_path.open("r", encoding="utf-8") as file:
        for line_no, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            poi_id = str(row.get("poi_id") or row.get("id") or f"ugc_poi_{line_no:06d}")
            source = str(row.get("source") or "ugc")
            tags = _text_join(row.get("tags"))
            reviews = row.get("reviews")
            items = reviews if isinstance(reviews, list) else [row]
            for index, item in enumerate(items, start=1):
                if not isinstance(item, dict):
                    continue
                content = str(item.get("content") or item.get("text") or item.get("quote") or "").strip()
                if not content:
                    continue
                rating = _float(item.get("rating"), default=_float(row.get("poi_rating"), default=4.0))
                score = rating + min(len(content), 240) / 240
                grouped[poi_id].append(
                    {
                        "poi_id": poi_id,
                        "snippet": _snippet(content),
                        "source": source,
                        "score": round(score, 4),
                        "tags_text": tags,
                        "source_order": index,
                    }
                )

    rows: list[dict[str, Any]] = []
    summaries: dict[str, str] = {}
    for poi_id, items in grouped.items():
        ranked = sorted(items, key=lambda item: item["score"], reverse=True)[:3]
        summaries[poi_id] = " ".join(item["snippet"] for item in ranked)
        for rank, item in enumerate(ranked, start=1):
            rows.append(
                {
                    "poi_id": poi_id,
                    "rank": rank,
                    "snippet": item["snippet"],
                    "source": item["source"],
                    "score": item["score"],
                    "tags_text": item["tags_text"],
                }
            )
    return rows, summaries


def _drop_derived_tables(conn: sqlite3.Connection) -> None:
    for table in DERIVED_TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table}")


def _create_derived_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE poi_feature_index (
          poi_id TEXT PRIMARY KEY,
          city TEXT NOT NULL,
          category TEXT NOT NULL,
          derived_category TEXT NOT NULL,
          district TEXT,
          business_area TEXT,
          price_band TEXT NOT NULL,
          queue_band TEXT NOT NULL,
          rating_score REAL NOT NULL,
          popularity_score REAL NOT NULL,
          static_score REAL NOT NULL,
          is_meal_candidate INTEGER NOT NULL,
          is_experience_candidate INTEGER NOT NULL,
          is_low_queue INTEGER NOT NULL,
          is_photo_friendly INTEGER NOT NULL,
          tags_text TEXT NOT NULL,
          keywords_text TEXT NOT NULL
        );

        CREATE INDEX idx_poi_feature_city_score
          ON poi_feature_index(city, static_score DESC);
        CREATE INDEX idx_poi_feature_city_category
          ON poi_feature_index(city, category, static_score DESC);
        CREATE INDEX idx_poi_feature_price_queue
          ON poi_feature_index(city, price_band, queue_band);

        CREATE VIRTUAL TABLE poi_retrieval_fts USING fts5(
          poi_id UNINDEXED,
          name,
          category,
          district,
          search_text,
          tokenize = 'unicode61'
        );

        CREATE TABLE poi_bucket_top (
          scenario_key TEXT NOT NULL,
          poi_id TEXT NOT NULL,
          city TEXT NOT NULL,
          rank INTEGER NOT NULL,
          score REAL NOT NULL,
          PRIMARY KEY (scenario_key, poi_id)
        );
        CREATE INDEX idx_poi_bucket_lookup
          ON poi_bucket_top(city, scenario_key, rank);

        CREATE TABLE ugc_evidence_index (
          poi_id TEXT NOT NULL,
          rank INTEGER NOT NULL,
          snippet TEXT NOT NULL,
          source TEXT NOT NULL,
          score REAL NOT NULL,
          tags_text TEXT NOT NULL,
          PRIMARY KEY (poi_id, rank)
        );
        CREATE INDEX idx_ugc_evidence_poi
          ON ugc_evidence_index(poi_id, rank);
        """
    )


def _feature_row(poi: dict[str, Any], ugc_summary: str) -> dict[str, Any]:
    tags = _json_list(poi.get("tags_json"))
    keywords = _json_list(poi.get("high_freq_keywords_json"))
    suitable_for = _json_list(poi.get("suitable_for_json"))
    atmosphere = _json_list(poi.get("atmosphere_json"))
    queue = _json_object(poi.get("queue_estimate_json"))
    weekend_queue = _int(queue.get("weekend_peak"), default=35)
    rating = _float(poi.get("rating"), default=4.0)
    review_count = _int(poi.get("review_count"), default=0)
    price = _int(poi.get("price_per_person"), default=None)
    category = str(poi.get("category") or "restaurant")
    sub_category = str(poi.get("sub_category") or "")
    district = str(poi.get("district") or "")
    business_area = str(poi.get("business_area") or "")
    tags_text = _text_join([sub_category, district, business_area, tags, suitable_for, atmosphere])
    keywords_text = _text_join(keywords)
    rating_score = max(0.0, min(rating / 5, 1.0))
    popularity_score = max(0.0, min(math.log1p(review_count) / math.log1p(1200), 1.0))
    queue_bonus = max(0.0, (60 - min(weekend_queue, 60)) / 60)
    price_bonus = 0.55 if price is None else max(0.0, (260 - min(price, 260)) / 260)
    static_score = round(rating_score * 0.42 + popularity_score * 0.18 + queue_bonus * 0.24 + price_bonus * 0.16, 6)
    search_text = _text_join(
        [
            poi.get("name"),
            category,
            sub_category,
            district,
            business_area,
            tags_text,
            keywords_text,
            ugc_summary,
        ]
    )
    search_text = f"{search_text} {' '.join(_ngrams(search_text))}"
    is_photo = int(
        category in {"scenic", "culture"}
        or any(token in search_text.lower() for token in ["photo", "photogenic", "拍照", "出片", "风景", "公园"])
    )
    return {
        "poi_id": str(poi["id"]),
        "name": str(poi.get("name") or poi["id"]),
        "city": str(poi.get("city") or "hefei"),
        "category": category,
        "derived_category": _derived_category(category, sub_category),
        "district": district,
        "business_area": business_area,
        "price_band": _price_band(price),
        "queue_band": _queue_band(weekend_queue),
        "rating_score": round(rating_score, 6),
        "popularity_score": round(popularity_score, 6),
        "static_score": static_score,
        "is_meal_candidate": int(category == "restaurant"),
        "is_experience_candidate": int(category in EXPERIENCE_CATEGORIES),
        "is_low_queue": int(weekend_queue <= 25),
        "is_photo_friendly": is_photo,
        "tags_text": tags_text,
        "keywords_text": keywords_text,
        "search_text": search_text,
    }


def _bucket_rows(feature_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scenarios = {
        "local_food": lambda row: row["category"] == "restaurant",
        "low_queue_food": lambda row: row["category"] == "restaurant" and row["is_low_queue"],
        "photo_walk": lambda row: row["is_photo_friendly"] or row["category"] in {"scenic", "culture"},
        "couple_photo_food": lambda row: row["is_photo_friendly"] or row["category"] in {"restaurant", "cafe"},
        "low_budget": lambda row: row["price_band"] in {"free", "low", "unknown"},
        "scenic": lambda row: row["category"] == "scenic",
        "shopping": lambda row: row["category"] == "shopping",
    }
    rows: list[dict[str, Any]] = []
    for scenario, predicate in scenarios.items():
        candidates = [row for row in feature_rows if predicate(row)]
        candidates.sort(key=lambda row: row["static_score"], reverse=True)
        for rank, row in enumerate(candidates[:400], start=1):
            rows.append(
                {
                    "scenario_key": scenario,
                    "poi_id": row["poi_id"],
                    "city": row["city"],
                    "rank": rank,
                    "score": row["static_score"],
                }
            )
    return rows


def _derived_category(category: str, sub_category: str) -> str:
    text = f"{category} {sub_category}".lower()
    if category in {"scenic", "shopping", "culture", "cafe", "nightlife", "entertainment"}:
        return category
    if any(keyword in text for keyword in ["coffee", "cafe", "咖啡"]):
        return "cafe"
    return category


def _price_band(price: int | None) -> str:
    if price is None:
        return "unknown"
    if price <= 0:
        return "free"
    if price <= 80:
        return "low"
    if price <= 180:
        return "mid"
    return "high"


def _queue_band(queue: int) -> str:
    if queue <= 15:
        return "none"
    if queue <= 30:
        return "low"
    if queue <= 45:
        return "mid"
    return "high"


def _json_list(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if not raw:
        return []
    try:
        value = json.loads(str(raw))
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def _json_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        value = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _text_join(values: Any) -> str:
    parts: list[str] = []

    def append(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, dict):
            for item in value.values():
                append(item)
            return
        if isinstance(value, list):
            for item in value:
                append(item)
            return
        if isinstance(value, tuple):
            for item in value:
                append(item)
            return
        text = str(value).strip()
        if text:
            parts.append(text)

    append(values)
    return " ".join(dict.fromkeys(parts))


def _ngrams(text: str) -> list[str]:
    values: list[str] = []
    chinese = "".join(ch for ch in text if "\u4e00" <= ch <= "\u9fff")
    for size in (2, 3):
        for index in range(0, max(len(chinese) - size + 1, 0)):
            values.append(chinese[index : index + size])
    return values[:200]


def _snippet(content: str, limit: int = 140) -> str:
    content = " ".join(content.split())
    return content if len(content) <= limit else f"{content[:limit]}..."


def _float(value: Any, *, default: float) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, *, default: int | None) -> int | None:
    try:
        if value is None:
            return default
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def main() -> None:
    parser = argparse.ArgumentParser(description="Build SQLite retrieval indexes for AIroute.")
    parser.add_argument("--main-db", type=Path, default=DEFAULT_MAIN_DB)
    parser.add_argument("--ugc", type=Path, default=DEFAULT_UGC_PATH)
    parser.add_argument("--source-db", action="append", type=Path, dest="source_dbs")
    args = parser.parse_args()
    stats = build_retrieval_index(
        main_db_path=args.main_db,
        source_db_paths=args.source_dbs or DEFAULT_SOURCE_DBS,
        ugc_path=args.ugc,
    )
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()

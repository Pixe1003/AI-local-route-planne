from __future__ import annotations

import argparse
import ast
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_INPUT = Path("C:/Users/86187/Desktop/合肥餐饮POI.xlsx")
DEFAULT_OUTPUT = Path("data/processed/hefei_pois.sqlite")
SHEET_NAME = "合肥餐饮POI"

X_PI = math.pi * 3000.0 / 180.0
PI = math.pi
A = 6378245.0
EE = 0.00669342162296594323


def out_of_china(lon: float, lat: float) -> bool:
    return not (72.004 <= lon <= 137.8347 and 0.8293 <= lat <= 55.8271)


def transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * PI) + 40.0 * math.sin(y / 3.0 * PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * PI) + 320 * math.sin(y * PI / 30.0)) * 2.0 / 3.0
    return ret


def transform_lon(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * PI) + 40.0 * math.sin(x / 3.0 * PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * PI) + 300.0 * math.sin(x / 30.0 * PI)) * 2.0 / 3.0
    return ret


def wgs84_to_gcj02(lon: float, lat: float) -> tuple[float, float]:
    if out_of_china(lon, lat):
        return lon, lat
    dlat = transform_lat(lon - 105.0, lat - 35.0)
    dlon = transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * PI
    magic = math.sin(radlat)
    magic = 1 - EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((A * (1 - EE)) / (magic * sqrt_magic) * PI)
    dlon = (dlon * 180.0) / (A / sqrt_magic * math.cos(radlat) * PI)
    return lon + dlon, lat + dlat


def parse_biz_ext(raw: Any) -> dict[str, Any]:
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return {}
    if not isinstance(raw, str):
        return {}
    text = raw.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}


def clean_float(value: Any, *, default: float | None = None) -> float | None:
    if value is None or value == "" or value == []:
        return default
    try:
        if isinstance(value, float) and math.isnan(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def clean_int(value: Any, *, default: int | None = None) -> int | None:
    number = clean_float(value)
    if number is None:
        return default
    return int(round(number))


def text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    if not text or text == "[]":
        return None
    return text


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def category_tags(row: pd.Series) -> list[str]:
    tags = ["hefei", "餐饮"]
    for col in ("行业大", "行业中", "行业小", "adname", "business_a"):
        value = text_or_none(row.get(col))
        if value:
            tags.append(value)
    return list(dict.fromkeys(tags))


def queue_estimate(row: pd.Series, price_per_person: int | None, rating: float) -> dict[str, int]:
    sub_category = text_or_none(row.get("行业小")) or ""
    base = 20
    if any(keyword in sub_category for keyword in ("火锅", "特色", "海鲜", "综合酒楼", "地方风味")):
        base += 10
    if rating >= 4.5:
        base += 8
    if price_per_person and price_per_person >= 120:
        base += 5
    return {
        "weekday_peak": max(5, min(base, 55)),
        "weekend_peak": max(8, min(base + 12, 75)),
    }


def visit_duration(row: pd.Series) -> int:
    sub_category = text_or_none(row.get("行业小")) or ""
    if any(keyword in sub_category for keyword in ("咖啡", "冷饮", "甜品", "糕饼", "茶艺")):
        return 40
    if any(keyword in sub_category for keyword in ("火锅", "酒楼", "海鲜", "外国餐厅", "日本料理", "韩国料理")):
        return 75
    return 55


def suitable_for(row: pd.Series) -> list[str]:
    sub_category = text_or_none(row.get("行业小")) or ""
    values = ["friends", "foodie"]
    if any(keyword in sub_category for keyword in ("咖啡", "甜品", "冷饮", "茶艺")):
        values.extend(["couple", "solo"])
    if any(keyword in sub_category for keyword in ("火锅", "酒楼", "海鲜")):
        values.append("group")
    return list(dict.fromkeys(values))


def atmosphere(row: pd.Series) -> list[str]:
    sub_category = text_or_none(row.get("行业小")) or ""
    if any(keyword in sub_category for keyword in ("咖啡", "茶艺", "甜品")):
        return ["relaxed", "photogenic"]
    if any(keyword in sub_category for keyword in ("快餐", "冷饮", "糕饼")):
        return ["casual", "quick"]
    return ["lively"]


def keyword_rows(poi_id: str, tags: list[str]) -> list[tuple[str, str, int]]:
    rows = []
    for index, keyword in enumerate(tags[:8]):
        rows.append((poi_id, keyword, max(1, 80 - index * 7)))
    return rows


def build_record(row: pd.Series) -> dict[str, Any] | None:
    source_id = text_or_none(row.get("id"))
    name = text_or_none(row.get("name"))
    lon_wgs84 = clean_float(row.get("经度"))
    lat_wgs84 = clean_float(row.get("纬度"))
    if not source_id or not name or lon_wgs84 is None or lat_wgs84 is None:
        return None

    lon_gcj02, lat_gcj02 = wgs84_to_gcj02(lon_wgs84, lat_wgs84)
    biz_ext = parse_biz_ext(row.get("biz_ext"))
    rating = clean_float(biz_ext.get("rating"), default=4.0) or 4.0
    if rating <= 0 or rating > 5:
        rating = 4.0
    price = clean_int(biz_ext.get("cost"))
    if price is not None and (price <= 0 or price > 1000):
        price = None

    tags = category_tags(row)
    poi_id = f"hf_poi_{int(row['FID']):06d}" if clean_int(row.get("FID")) is not None else f"hf_{source_id}"
    district = text_or_none(row.get("adname"))
    business_area = text_or_none(row.get("business_a"))
    sub_category = text_or_none(row.get("行业小")) or text_or_none(row.get("行业中")) or "餐饮"
    timestamp = text_or_none(row.get("timestamp"))

    return {
        "id": poi_id,
        "source": "hefei_excel",
        "source_poi_id": source_id,
        "name": name,
        "city": "hefei",
        "category": "restaurant",
        "sub_category": sub_category,
        "type": text_or_none(row.get("type")),
        "typecode": text_or_none(row.get("typecode")),
        "address": text_or_none(row.get("address")),
        "province_code": text_or_none(row.get("pcode")),
        "province_name": text_or_none(row.get("pname")),
        "city_code": text_or_none(row.get("citycode")),
        "city_name": text_or_none(row.get("cityname")),
        "adcode": text_or_none(row.get("adcode")),
        "district": district,
        "business_area": business_area,
        "longitude_wgs84": lon_wgs84,
        "latitude_wgs84": lat_wgs84,
        "longitude_gcj02": lon_gcj02,
        "latitude_gcj02": lat_gcj02,
        "rating": rating,
        "price_per_person": price,
        "review_count": 0,
        "open_hours_json": json_text({}),
        "queue_estimate_json": json_text(queue_estimate(row, price, rating)),
        "tags_json": json_text(tags),
        "high_freq_keywords_json": json_text(
            [{"keyword": keyword, "count": count} for _, keyword, count in keyword_rows(poi_id, tags)]
        ),
        "suitable_for_json": json_text(suitable_for(row)),
        "atmosphere_json": json_text(atmosphere(row)),
        "visit_duration": visit_duration(row),
        "cover_image": None,
        "source_updated_at": timestamp,
    }


SCHEMA = """
DROP TABLE IF EXISTS poi_keywords;
DROP TABLE IF EXISTS pois;
DROP VIEW IF EXISTS app_pois;

CREATE TABLE pois (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  source_poi_id TEXT,
  name TEXT NOT NULL,
  city TEXT NOT NULL,
  category TEXT NOT NULL,
  sub_category TEXT,
  type TEXT,
  typecode TEXT,
  address TEXT,
  province_code TEXT,
  province_name TEXT,
  city_code TEXT,
  city_name TEXT,
  adcode TEXT,
  district TEXT,
  business_area TEXT,
  longitude_wgs84 REAL NOT NULL,
  latitude_wgs84 REAL NOT NULL,
  longitude_gcj02 REAL NOT NULL,
  latitude_gcj02 REAL NOT NULL,
  rating REAL NOT NULL DEFAULT 4.0,
  price_per_person INTEGER,
  review_count INTEGER NOT NULL DEFAULT 0,
  open_hours_json TEXT NOT NULL DEFAULT '{}',
  queue_estimate_json TEXT NOT NULL DEFAULT '{}',
  tags_json TEXT NOT NULL DEFAULT '[]',
  high_freq_keywords_json TEXT NOT NULL DEFAULT '[]',
  suitable_for_json TEXT NOT NULL DEFAULT '[]',
  atmosphere_json TEXT NOT NULL DEFAULT '[]',
  visit_duration INTEGER NOT NULL DEFAULT 55,
  cover_image TEXT,
  source_updated_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE poi_keywords (
  poi_id TEXT NOT NULL REFERENCES pois(id) ON DELETE CASCADE,
  keyword TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (poi_id, keyword)
);

CREATE INDEX idx_pois_city_category ON pois(city, category);
CREATE INDEX idx_pois_district ON pois(district);
CREATE INDEX idx_pois_sub_category ON pois(sub_category);
CREATE INDEX idx_pois_rating ON pois(rating);
CREATE INDEX idx_pois_price ON pois(price_per_person);
CREATE INDEX idx_pois_gcj_location ON pois(latitude_gcj02, longitude_gcj02);
CREATE INDEX idx_poi_keywords_keyword ON poi_keywords(keyword);

CREATE VIEW app_pois AS
SELECT
  id,
  name,
  city,
  category,
  sub_category,
  address,
  latitude_gcj02 AS latitude,
  longitude_gcj02 AS longitude,
  rating,
  price_per_person,
  open_hours_json,
  tags_json,
  cover_image,
  review_count,
  queue_estimate_json,
  visit_duration,
  high_freq_keywords_json,
  suitable_for_json,
  atmosphere_json,
  district,
  business_area
FROM pois;
"""


def import_pois(input_path: Path, output_path: Path) -> None:
    df = pd.read_excel(input_path, sheet_name=SHEET_NAME)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    records: list[dict[str, Any]] = []
    keywords: list[tuple[str, str, int]] = []
    for _, row in df.iterrows():
        record = build_record(row)
        if record is None:
            continue
        records.append(record)
        tags = json.loads(record["tags_json"])
        keywords.extend(keyword_rows(record["id"], tags))

    with sqlite3.connect(output_path) as conn:
        conn.executescript(SCHEMA)
        columns = list(records[0].keys())
        placeholders = ",".join(["?"] * len(columns))
        conn.executemany(
            f"INSERT INTO pois ({','.join(columns)}) VALUES ({placeholders})",
            [[record[column] for column in columns] for record in records],
        )
        conn.executemany(
            "INSERT OR REPLACE INTO poi_keywords (poi_id, keyword, count) VALUES (?, ?, ?)",
            keywords,
        )
        conn.execute(
            "CREATE TABLE import_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.executemany(
            "INSERT INTO import_meta (key, value) VALUES (?, ?)",
            [
                ("source_file", str(input_path)),
                ("sheet_name", SHEET_NAME),
                ("source_rows", str(len(df))),
                ("imported_pois", str(len(records))),
                ("coordinate_source", "WGS84"),
                ("coordinate_runtime", "GCJ-02"),
                ("imported_at", datetime.now(timezone.utc).isoformat()),
            ],
        )
        conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Hefei restaurant POIs into SQLite.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    import_pois(args.input, args.output)
    print(f"Imported POIs into {args.output}")


if __name__ == "__main__":
    main()

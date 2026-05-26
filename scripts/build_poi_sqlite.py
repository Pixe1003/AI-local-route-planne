from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import httpx

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.category_policy import normalize_category  # noqa: E402


OPEN_HOURS = {
    day: [{"open": "09:00", "close": "22:00"}]
    for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
}

DISTRICT_CENTROIDS: dict[str, tuple[float, float]] = {
    "庐阳区": (31.8784, 117.2647),
    "蜀山区": (31.8512, 117.229),
    "包河区": (31.7939, 117.3096),
    "瑶海区": (31.8696, 117.3153),
    "经开区": (31.7848, 117.2298),
    "高新区": (31.8424, 117.1351),
    "滨湖新区": (31.7362, 117.2853),
    "肥西县": (31.707, 117.1584),
    "肥东县": (31.8877, 117.4694),
    "长丰县": (32.4783, 117.1676),
}
DEFAULT_CENTER = (31.8206, 117.2272)


class Geocoder(Protocol):
    def geocode(self, row: dict[str, Any]) -> tuple[float, float] | None:
        ...


@dataclass
class AmapGeocoder:
    key: str
    city: str = "合肥"
    cache_path: Path | None = None
    timeout_seconds: int = 8
    sleep_seconds: float = 0.1

    def __post_init__(self) -> None:
        self._cache: dict[str, dict[str, Any]] = {}
        if self.cache_path and self.cache_path.exists():
            self._cache = json.loads(self.cache_path.read_text(encoding="utf-8"))

    def geocode(self, row: dict[str, Any]) -> tuple[float, float] | None:
        poi_id = str(row["poi_id"])
        cached = self._cache.get(poi_id)
        if cached and cached.get("latitude") is not None and cached.get("longitude") is not None:
            return float(cached["latitude"]), float(cached["longitude"])
        if not self.key:
            return None

        location = self._place_search(row) or self._geo_code(row)
        if location is not None:
            self._cache[poi_id] = {
                "latitude": location[0],
                "longitude": location[1],
                "source": "amap",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            time.sleep(self.sleep_seconds)
            return location
        self._cache[poi_id] = {
            "latitude": None,
            "longitude": None,
            "source": "unmatched",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        time.sleep(self.sleep_seconds)
        return None

    def save(self) -> None:
        if not self.cache_path:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(self._cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _place_search(self, row: dict[str, Any]) -> tuple[float, float] | None:
        try:
            response = httpx.get(
                "https://restapi.amap.com/v3/place/text",
                params={
                    "key": self.key,
                    "keywords": row["poi_name"],
                    "city": self.city,
                    "citylimit": "true",
                    "offset": 1,
                    "page": 1,
                    "extensions": "base",
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return None
        pois = payload.get("pois") if isinstance(payload, dict) else None
        if not isinstance(pois, list) or not pois:
            return None
        return _parse_amap_location(pois[0].get("location"))

    def _geo_code(self, row: dict[str, Any]) -> tuple[float, float] | None:
        address = f"{self.city}{row.get('district') or ''}{row['poi_name']}"
        try:
            response = httpx.get(
                "https://restapi.amap.com/v3/geocode/geo",
                params={"key": self.key, "address": address, "city": self.city},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return None
        geocodes = payload.get("geocodes") if isinstance(payload, dict) else None
        if not isinstance(geocodes, list) or not geocodes:
            return None
        return _parse_amap_location(geocodes[0].get("location"))


def build_sqlite(
    *,
    city: str,
    source: str | Path,
    out: str | Path,
    geocoder: Geocoder | None = None,
    reset: bool = False,
) -> dict[str, int]:
    source_path = Path(source)
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    existing_coordinates = _load_existing_coordinates(out_path)
    if reset and out_path.exists():
        out_path.chmod(0o666)
        out_path.unlink()

    rows = [_normalize_source_row(row, city) for row in _read_jsonl(source_path)]
    con = sqlite3.connect(out_path)
    try:
        _create_schema(con)
        stats = {
            "source_rows": 0,
            "app_pois": 0,
            "geocoded": 0,
            "estimated": 0,
            "ugc_evidence_rows": 0,
        }
        for row in rows:
            stats["source_rows"] += 1
            coordinate = existing_coordinates.get(row["poi_id"])
            source_kind = "existing"
            if coordinate is None and geocoder is not None and _should_geocode(row):
                coordinate = geocoder.geocode(row)
                if coordinate is not None:
                    stats["geocoded"] += 1
                    source_kind = "amap"
            if coordinate is None:
                coordinate = _estimated_coordinate(row)
                stats["estimated"] += 1
                source_kind = "district_estimate"
            app_row = _app_poi_row(row, coordinate)
            con.execute(_INSERT_APP_POI, app_row)
            con.execute(_INSERT_FEATURE, _feature_row(row, source_kind))
            evidence_rows = _evidence_rows(row)
            con.executemany(_INSERT_EVIDENCE, evidence_rows)
            stats["ugc_evidence_rows"] += len(evidence_rows)
            stats["app_pois"] += 1
        _insert_meta(con, city, stats)
        con.commit()
    finally:
        con.close()
    if hasattr(geocoder, "save"):
        geocoder.save()
    return stats


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def _normalize_source_row(row: dict[str, Any], city: str) -> dict[str, Any]:
    tags = _tokens_from_row(row)
    category = _derive_category(row, tags)
    return {
        "poi_id": str(row["poi_id"]),
        "poi_name": str(row["poi_name"]).strip(),
        "city": city,
        "category": category,
        "sub_category": str(row.get("sub_category") or category),
        "district": str(row.get("district") or ""),
        "rating": float(row.get("poi_rating") or 4.0),
        "price_per_person": row.get("price_per_person"),
        "reviews": row.get("reviews") if isinstance(row.get("reviews"), list) else [],
        "tags": tags,
    }


def _derive_category(row: dict[str, Any], tags: list[str]) -> str:
    poi_id = str(row.get("poi_id") or "")
    sub_category = str(row.get("sub_category") or "")
    if poi_id.startswith("hf_scenic_"):
        return "scenic"
    if poi_id.startswith("hf_shopping_"):
        return "shopping"
    return normalize_category("restaurant", sub_category, tags)


def _tokens_from_row(row: dict[str, Any]) -> list[str]:
    tokens = [
        "hefei",
        str(row.get("district") or ""),
        str(row.get("sub_category") or ""),
    ]
    for review in row.get("reviews") or []:
        content = str(review.get("content") or "")
        for keyword in ["少排队", "拍照", "散步", "文艺", "商场", "购物", "公园", "徽菜", "咖啡"]:
            if keyword in content:
                tokens.append(keyword)
    return list(dict.fromkeys(token for token in tokens if token))


def _should_geocode(row: dict[str, Any]) -> bool:
    return row["category"] in {"scenic", "shopping", "culture", "entertainment", "outdoor", "nightlife"}


def _estimated_coordinate(row: dict[str, Any]) -> tuple[float, float]:
    base = DISTRICT_CENTROIDS.get(row["district"], DEFAULT_CENTER)
    digest = hashlib.sha1(row["poi_id"].encode("utf-8")).digest()
    lat_jitter = ((digest[0] / 255) - 0.5) * 0.04
    lng_jitter = ((digest[1] / 255) - 0.5) * 0.04
    return round(base[0] + lat_jitter, 6), round(base[1] + lng_jitter, 6)


def _app_poi_row(row: dict[str, Any], coordinate: tuple[float, float]) -> tuple[Any, ...]:
    latitude, longitude = coordinate
    keywords = _keywords(row)
    queue = _queue_estimate(row["category"])
    return (
        row["poi_id"],
        row["poi_name"],
        row["city"],
        row["category"],
        row["sub_category"],
        _address(row),
        latitude,
        longitude,
        row["rating"],
        _price(row),
        json.dumps(OPEN_HOURS, ensure_ascii=False),
        json.dumps(row["tags"], ensure_ascii=False),
        None,
        max(20, len(row["reviews"]) * 120),
        json.dumps(queue, ensure_ascii=False),
        _visit_duration(row["category"]),
        json.dumps(keywords, ensure_ascii=False),
        json.dumps(_suitable_for(row["category"]), ensure_ascii=False),
        json.dumps(_atmosphere(row["category"]), ensure_ascii=False),
        row["district"],
        row["district"],
    )


def _feature_row(row: dict[str, Any], coordinate_source: str) -> tuple[Any, ...]:
    queue = _queue_estimate(row["category"])
    rating_score = min(max(row["rating"] / 5, 0), 1)
    popularity_score = min(len(row["reviews"]) / 8, 1)
    static_score = round(rating_score * 0.65 + popularity_score * 0.2 + 0.15, 4)
    tags_text = " ".join([*row["tags"], coordinate_source])
    keywords_text = " ".join(item["keyword"] for item in _keywords(row))
    return (
        row["poi_id"],
        row["city"],
        row["category"],
        row["category"],
        row["district"],
        row["district"],
        _price_band(_price(row)),
        "low" if queue["weekend_peak"] <= 25 else "medium",
        round(rating_score, 4),
        round(popularity_score, 4),
        static_score,
        1 if row["category"] in {"restaurant", "cafe"} else 0,
        1 if row["category"] not in {"restaurant", "cafe"} else 0,
        1 if queue["weekend_peak"] <= 25 else 0,
        1 if row["category"] in {"scenic", "shopping", "cafe"} else 0,
        tags_text,
        keywords_text,
    )


def _evidence_rows(row: dict[str, Any]) -> list[tuple[Any, ...]]:
    evidence = []
    for index, review in enumerate((row["reviews"] or [])[:3]):
        snippet = str(review.get("content") or "").strip()
        if not snippet:
            continue
        evidence.append(
            (
                row["poi_id"],
                index + 1,
                snippet,
                "ugc",
                float(review.get("rating") or row["rating"]),
                " ".join(row["tags"]),
            )
        )
    if not evidence:
        evidence.append(
            (
                row["poi_id"],
                1,
                f"{row['poi_name']}位于{row['district']}，适合本地路线串联。",
                "generated_profile",
                row["rating"],
                " ".join(row["tags"]),
            )
        )
    return evidence


def _keywords(row: dict[str, Any]) -> list[dict[str, Any]]:
    keywords = [row["sub_category"], row["category"], row["district"], *row["tags"]]
    return [
        {"keyword": keyword, "count": max(20, 90 - index * 8)}
        for index, keyword in enumerate(dict.fromkeys(item for item in keywords if item))
    ][:8]


def _queue_estimate(category: str) -> dict[str, int]:
    if category == "restaurant":
        return {"weekday_peak": 20, "weekend_peak": 32}
    if category == "cafe":
        return {"weekday_peak": 10, "weekend_peak": 18}
    return {"weekday_peak": 8, "weekend_peak": 16}


def _visit_duration(category: str) -> int:
    return {"restaurant": 70, "cafe": 45, "shopping": 75, "scenic": 75}.get(category, 60)


def _suitable_for(category: str) -> list[str]:
    if category == "restaurant":
        return ["friends", "foodie", "couple"]
    if category == "shopping":
        return ["friends", "couple", "solo", "photographer"]
    return ["friends", "couple", "solo", "parent_child", "photographer"]


def _atmosphere(category: str) -> list[str]:
    if category == "restaurant":
        return ["lively", "local"]
    if category == "cafe":
        return ["relaxed", "photogenic"]
    if category == "shopping":
        return ["indoor", "citywalk"]
    return ["outdoor", "photogenic", "relaxed"]


def _price(row: dict[str, Any]) -> int | None:
    value = row.get("price_per_person")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _price_band(price: int | None) -> str:
    if price is None:
        return "unknown"
    if price <= 50:
        return "low"
    if price <= 120:
        return "medium"
    return "high"


def _address(row: dict[str, Any]) -> str:
    return f"合肥市{row['district']}{row['poi_name']}"


def _parse_amap_location(value: object) -> tuple[float, float] | None:
    if not isinstance(value, str) or "," not in value:
        return None
    try:
        longitude, latitude = (float(item) for item in value.split(",", 1))
    except ValueError:
        return None
    return latitude, longitude


def _load_existing_coordinates(path: Path) -> dict[str, tuple[float, float]]:
    if not path.exists():
        return {}
    try:
        con = sqlite3.connect(path)
        rows = con.execute("select id, latitude, longitude from app_pois").fetchall()
    except sqlite3.Error:
        return {}
    finally:
        try:
            con.close()
        except UnboundLocalError:
            pass
    return {
        str(row[0]): (float(row[1]), float(row[2]))
        for row in rows
        if row[1] is not None and row[2] is not None
    }


def _create_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        create table if not exists app_pois (
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
        );
        create table if not exists poi_feature_index (
            poi_id text primary key,
            city text not null,
            category text not null,
            derived_category text not null,
            district text,
            business_area text,
            price_band text not null,
            queue_band text not null,
            rating_score real not null,
            popularity_score real not null,
            static_score real not null,
            is_meal_candidate integer not null,
            is_experience_candidate integer not null,
            is_low_queue integer not null,
            is_photo_friendly integer not null,
            tags_text text not null,
            keywords_text text not null
        );
        create table if not exists ugc_evidence_index (
            poi_id text not null,
            rank integer not null,
            snippet text not null,
            source text not null,
            score real not null,
            tags_text text not null,
            primary key (poi_id, rank)
        );
        create table if not exists import_meta (
            key text primary key,
            value text not null
        );
        """
    )


def _insert_meta(con: sqlite3.Connection, city: str, stats: dict[str, int]) -> None:
    meta = {
        "city": city,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "coordinate_runtime": "amap_or_district_estimate",
        **{key: str(value) for key, value in stats.items()},
    }
    con.executemany(
        "insert or replace into import_meta(key, value) values(?, ?)",
        list(meta.items()),
    )


_INSERT_APP_POI = """
insert or replace into app_pois values (
    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
)
"""

_INSERT_FEATURE = """
insert or replace into poi_feature_index values (
    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
)
"""

_INSERT_EVIDENCE = """
insert or replace into ugc_evidence_index values (?, ?, ?, ?, ?, ?)
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", default="hefei")
    parser.add_argument("--source", default="data/processed/ugc_hefei.jsonl")
    parser.add_argument("--out", default="data/processed/hefei_pois.sqlite")
    parser.add_argument("--geocode-cache", default="data/processed/amap_geocode_cache.json")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    key = os.getenv("AMAP_KEY", "")
    geocoder = AmapGeocoder(
        key=key,
        city="合肥" if args.city == "hefei" else args.city,
        cache_path=Path(args.geocode_cache),
    )
    stats = build_sqlite(
        city=args.city,
        source=args.source,
        out=args.out,
        geocoder=geocoder,
        reset=args.reset,
    )
    print(json.dumps(stats, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

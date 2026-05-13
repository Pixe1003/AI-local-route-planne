from functools import lru_cache
import json
import sqlite3
from pathlib import Path
from typing import Iterable, Optional

from app.repositories.seed_data import load_seed_pois
from app.schemas.poi import HighlightQuote, PoiDetail


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_POI_DB_PATH = PROJECT_ROOT / "data" / "processed" / "hefei_pois.sqlite"


class PoiRepository:
    def __init__(self) -> None:
        self._pois = self._load_pois()

    def _load_pois(self) -> dict[str, PoiDetail]:
        if DEFAULT_POI_DB_PATH.exists():
            pois = self._load_sqlite_pois(DEFAULT_POI_DB_PATH)
            if pois:
                seed_pois = {poi.id: poi for poi in load_seed_pois()}
                return {**seed_pois, **pois}
        return {poi.id: poi for poi in load_seed_pois()}

    def _load_sqlite_pois(self, db_path: Path) -> dict[str, PoiDetail]:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT
                  id, name, city, category, sub_category, address,
                  latitude, longitude, rating, price_per_person,
                  open_hours_json, tags_json, cover_image, review_count,
                  queue_estimate_json, visit_duration, high_freq_keywords_json,
                  suitable_for_json, atmosphere_json, district, business_area
                FROM app_pois
                """
            ).fetchall()
        return {poi.id: poi for poi in (self._row_to_poi(row) for row in rows)}

    def _row_to_poi(self, row: sqlite3.Row) -> PoiDetail:
        tags = _json_list(row["tags_json"])
        keywords = _json_list(row["high_freq_keywords_json"])
        sub_category = row["sub_category"] or "餐饮"
        district = row["district"] or "合肥"
        business_area = row["business_area"]
        name = row["name"]
        highlight = f"{name}位于{district}{f' · {business_area}' if business_area else ''}，适合作为合肥餐饮路线候选。"
        return PoiDetail(
            id=row["id"],
            name=name,
            city=row["city"],
            category=row["category"],
            sub_category=sub_category,
            address=row["address"] or f"合肥市{district}",
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            rating=float(row["rating"] or 4.0),
            price_per_person=row["price_per_person"],
            open_hours=_json_object(row["open_hours_json"])
            or {
                "monday": [{"open": "10:00", "close": "22:00"}],
                "tuesday": [{"open": "10:00", "close": "22:00"}],
                "wednesday": [{"open": "10:00", "close": "22:00"}],
                "thursday": [{"open": "10:00", "close": "22:00"}],
                "friday": [{"open": "10:00", "close": "22:30"}],
                "saturday": [{"open": "10:00", "close": "22:30"}],
                "sunday": [{"open": "10:00", "close": "22:00"}],
            },
            tags=tags or ["hefei", "餐饮", sub_category],
            cover_image=row["cover_image"],
            review_count=int(row["review_count"] or 0),
            queue_estimate=_json_int_dict(row["queue_estimate_json"])
            or {"weekday_peak": 20, "weekend_peak": 35},
            visit_duration=int(row["visit_duration"] or 55),
            best_time_slots=["weekday_evening", "weekend_afternoon"],
            avoid_time_slots=["weekend_noon"],
            highlight_quotes=[
                HighlightQuote(
                    quote=highlight,
                    source="hefei_excel",
                    category="location_recommendation",
                )
            ],
            high_freq_keywords=keywords or [{"keyword": sub_category, "count": 80}],
            hidden_menu=[],
            avoid_tips=["高峰时段建议提前确认营业和排队情况"],
            suitable_for=_json_list(row["suitable_for_json"]) or ["friends", "foodie"],
            atmosphere=_json_list(row["atmosphere_json"]) or ["lively"],
        )

    def list_by_city(self, city: str) -> list[PoiDetail]:
        return [poi for poi in self._pois.values() if poi.city == city]

    def get(self, poi_id: str) -> PoiDetail:
        return self._pois[poi_id]

    def get_many(self, poi_ids: Iterable[str]) -> list[PoiDetail]:
        return [self._pois[poi_id] for poi_id in poi_ids if poi_id in self._pois]

    def find_replacement(
        self,
        *,
        exclude_ids: set[str],
        category_hint: Optional[str],
        avoid_queue: bool = True,
    ) -> Optional[PoiDetail]:
        candidates = [poi for poi in self._pois.values() if poi.id not in exclude_ids]
        if category_hint:
            same_category = [poi for poi in candidates if poi.category == category_hint]
            if same_category:
                candidates = same_category
        if avoid_queue:
            candidates.sort(key=lambda poi: (poi.queue_estimate["weekend_peak"], -poi.rating))
        else:
            candidates.sort(key=lambda poi: (-poi.rating, poi.queue_estimate["weekend_peak"]))
        return candidates[0] if candidates else None


@lru_cache
def get_poi_repository() -> PoiRepository:
    return PoiRepository()


def _json_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def _json_object(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _json_int_dict(raw: str | None) -> dict[str, int]:
    value = _json_object(raw)
    result: dict[str, int] = {}
    for key, item in value.items():
        try:
            result[str(key)] = int(item)
        except (TypeError, ValueError):
            continue
    return result

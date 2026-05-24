import json
import sqlite3
from pathlib import Path
from typing import Any

from app.schemas.poi import HighlightQuote, PoiDetail
from app.services.category_policy import CATEGORY_ORDER, CANONICAL_CATEGORIES, normalize_category


def load_sqlite_pois(path: str | Path, city: str | None = None, limit: int | None = None) -> list[PoiDetail]:
    db_path = Path(path)
    if not db_path.exists():
        return []
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        if limit is not None:
            rows = _limited_rows(con, city, limit)
        else:
            sql = "select * from app_pois"
            params: tuple[Any, ...] = ()
            if city:
                sql += " where city = ?"
                params = (city,)
            rows = con.execute(sql, params).fetchall()
        feature_rows = _feature_rows(con, [row["id"] for row in rows])
        evidence_rows = _evidence_rows(con, [row["id"] for row in rows])
        return [
            _row_to_poi(
                row,
                feature=feature_rows.get(row["id"]),
                evidence=evidence_rows.get(row["id"], []),
            )
            for row in rows
        ]
    finally:
        con.close()


def load_sqlite_poi(path: str | Path, poi_id: str) -> PoiDetail | None:
    db_path = Path(path)
    if not db_path.exists():
        return None
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute("select * from app_pois where id = ?", (poi_id,)).fetchone()
        if row is None:
            return None
        return _row_to_poi(
            row,
            feature=_feature_rows(con, [poi_id]).get(poi_id),
            evidence=_evidence_rows(con, [poi_id]).get(poi_id, []),
        )
    finally:
        con.close()


def _limited_rows(con: sqlite3.Connection, city: str | None, limit: int) -> list[sqlite3.Row]:
    if _table_exists(con, "poi_feature_index"):
        return _limited_rows_with_features(con, city, limit)
    city_clause = "city = ?" if city else "1 = 1"
    params: tuple[Any, ...] = (city,) if city else ()
    priority_limit = max(20, limit // 3)
    priority_sql = f"""
        select * from app_pois
        where {city_clause}
          and (
            sub_category like '%茶艺%'
            or sub_category like '%咖啡%'
            or sub_category like '%冷饮%'
            or sub_category like '%甜品%'
            or sub_category like '%糕饼%'
            or sub_category like '%休闲餐饮%'
            or tags_json like '%文艺%'
            or tags_json like '%雨天友好%'
          )
        order by rating desc, review_count desc
        limit ?
    """
    rows = list(con.execute(priority_sql, (*params, priority_limit)).fetchall())
    seen = {row["id"] for row in rows}
    remaining = max(0, limit - len(rows))
    if remaining:
        general_sql = f"""
            select * from app_pois
            where {city_clause}
            order by rating desc, review_count desc
            limit ?
        """
        for row in con.execute(general_sql, (*params, remaining * 2)).fetchall():
            if row["id"] in seen:
                continue
            rows.append(row)
            seen.add(row["id"])
            if len(rows) >= limit:
                break
    return rows


def _limited_rows_with_features(
    con: sqlite3.Connection, city: str | None, limit: int
) -> list[sqlite3.Row]:
    city_clause = "p.city = ?" if city else "1 = 1"
    params: tuple[Any, ...] = (city,) if city else ()
    rows: list[sqlite3.Row] = []
    seen: set[str] = set()
    per_category = max(8, limit // max(len(CANONICAL_CATEGORIES), 1))
    for category in CATEGORY_ORDER:
        sql = f"""
            select p.* from app_pois p
            left join poi_feature_index f on f.poi_id = p.id
            where {city_clause}
              and coalesce(f.derived_category, p.category) = ?
            order by coalesce(f.static_score, 0) desc, p.rating desc, p.review_count desc
            limit ?
        """
        for row in con.execute(sql, (*params, category, per_category)).fetchall():
            if row["id"] in seen:
                continue
            rows.append(row)
            seen.add(row["id"])
            if len(rows) >= limit:
                return rows

    remaining = max(0, limit - len(rows))
    if remaining:
        general_sql = f"""
            select p.* from app_pois p
            left join poi_feature_index f on f.poi_id = p.id
            where {city_clause}
            order by coalesce(f.static_score, 0) desc, p.rating desc, p.review_count desc
            limit ?
        """
        for row in con.execute(general_sql, (*params, remaining * 3)).fetchall():
            if row["id"] in seen:
                continue
            rows.append(row)
            seen.add(row["id"])
            if len(rows) >= limit:
                break
    return rows


def _row_to_poi(
    row: sqlite3.Row,
    *,
    feature: sqlite3.Row | None = None,
    evidence: list[sqlite3.Row] | None = None,
) -> PoiDetail:
    tags = _json_list(row["tags_json"])
    keywords = _json_list(row["high_freq_keywords_json"])
    suitable_for = _json_list(row["suitable_for_json"])
    atmosphere = _json_list(row["atmosphere_json"])
    sub_category = row["sub_category"]
    feature_tags = _text_tokens(feature["tags_text"] if feature else "")
    feature_keywords = _text_tokens(feature["keywords_text"] if feature else "")
    district = row["district"] or (feature["district"] if feature else "") or ""
    business_area = row["business_area"] or (feature["business_area"] if feature else "") or ""
    category = normalize_category(
        row["category"],
        sub_category,
        [*tags, *feature_tags, *feature_keywords],
        derived_category=feature["derived_category"] if feature else None,
    )
    keyword_text = "、".join(str(item.get("keyword", "")) for item in keywords[:5] if item.get("keyword"))
    location_text = " / ".join(item for item in [district, business_area, row["address"]] if item)
    quote = f"POI 资料显示：{row['name']}位于{location_text}，高频关键词包括{keyword_text or sub_category or category}。"
    open_hours = _json_dict(row["open_hours_json"])
    queue_estimate = _json_dict(row["queue_estimate_json"]) or {"weekday_peak": 20, "weekend_peak": 32}
    highlight_quotes = _highlight_quotes_from_evidence(evidence or [])
    if not highlight_quotes:
        highlight_quotes = [
            HighlightQuote(quote=quote, source="poi_profile", review_date=None, category="poi_profile")
        ]
    else:
        highlight_quotes.append(
            HighlightQuote(quote=quote, source="poi_profile", review_date=None, category="poi_profile")
        )
    return PoiDetail(
        id=row["id"],
        name=row["name"],
        city=row["city"],
        category=category,
        sub_category=sub_category,
        address=row["address"] or "",
        latitude=float(row["latitude"]),
        longitude=float(row["longitude"]),
        rating=float(row["rating"] or 4.0),
        price_per_person=row["price_per_person"],
        open_hours=open_hours,
        tags=list(dict.fromkeys([*tags, district, business_area, sub_category])),
        cover_image=row["cover_image"],
        review_count=int(row["review_count"] or 0),
        queue_estimate={
            "weekday_peak": int(queue_estimate.get("weekday_peak", 20)),
            "weekend_peak": int(queue_estimate.get("weekend_peak", 32)),
        },
        visit_duration=int(row["visit_duration"] or 55),
        best_time_slots=["weekday_evening", "weekend_afternoon"],
        avoid_time_slots=[],
        highlight_quotes=highlight_quotes,
        high_freq_keywords=keywords,
        hidden_menu=[],
        avoid_tips=["缺少实时客流数据，建议到店前再次确认。"],
        suitable_for=suitable_for,
        atmosphere=atmosphere,
    )


def _highlight_quotes_from_evidence(rows: list[sqlite3.Row]) -> list[HighlightQuote]:
    quotes: list[HighlightQuote] = []
    for row in sorted(rows, key=lambda item: int(item["rank"] or 0)):
        snippet = str(row["snippet"] or "").strip()
        if not snippet:
            continue
        quotes.append(
            HighlightQuote(
                quote=snippet,
                source=str(row["source"] or "ugc"),
                review_date=None,
                category="ugc_review",
            )
        )
    return quotes


def _feature_rows(con: sqlite3.Connection, poi_ids: list[str]) -> dict[str, sqlite3.Row]:
    if not poi_ids or not _table_exists(con, "poi_feature_index"):
        return {}
    rows: dict[str, sqlite3.Row] = {}
    for chunk in _chunks(poi_ids):
        placeholders = ",".join("?" for _ in chunk)
        for row in con.execute(
            f"select * from poi_feature_index where poi_id in ({placeholders})",
            tuple(chunk),
        ).fetchall():
            rows[row["poi_id"]] = row
    return rows


def _evidence_rows(con: sqlite3.Connection, poi_ids: list[str]) -> dict[str, list[sqlite3.Row]]:
    if not poi_ids or not _table_exists(con, "ugc_evidence_index"):
        return {}
    rows: dict[str, list[sqlite3.Row]] = {}
    for chunk in _chunks(poi_ids):
        placeholders = ",".join("?" for _ in chunk)
        for row in con.execute(
            f"""
            select * from ugc_evidence_index
            where poi_id in ({placeholders})
            order by poi_id, rank
            """,
            tuple(chunk),
        ).fetchall():
            rows.setdefault(row["poi_id"], []).append(row)
    return rows


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "select 1 from sqlite_master where name = ? and type in ('table', 'view')",
        (name,),
    ).fetchone()
    return row is not None


def _chunks(items: list[str], size: int = 800):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _text_tokens(value: str | None) -> list[str]:
    if not value:
        return []
    return [token for token in value.replace("、", " ").split() if token]


def _json_list(value: str | None) -> list[Any]:
    parsed = _json(value, [])
    return parsed if isinstance(parsed, list) else []


def _json_dict(value: str | None) -> dict[str, Any]:
    parsed = _json(value, {})
    return parsed if isinstance(parsed, dict) else {}


def _json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "data" / "processed" / "hefei_pois.sqlite"
DEFAULT_OUT_PATH = PROJECT_ROOT / "data" / "processed" / "ugc_hefei.jsonl"

CATEGORY_LIMITS = {
    "restaurant": 36,
    "cafe": 12,
    "scenic": 12,
    "culture": 12,
    "shopping": 10,
    "entertainment": 8,
    "nightlife": 8,
    "outdoor": 8,
}

CATEGORY_TITLES = {
    "restaurant": "本地餐饮体验",
    "cafe": "中途休息体验",
    "scenic": "顺路打卡体验",
    "culture": "室内文化体验",
    "shopping": "逛街休息体验",
    "entertainment": "朋友聚会体验",
    "nightlife": "夜间收尾体验",
    "outdoor": "轻松散步体验",
}

INDOOR_CATEGORIES = {"restaurant", "cafe", "culture", "shopping", "entertainment", "nightlife"}


def generate_demo_ugc(
    *,
    sqlite_path: Path = DEFAULT_SQLITE_PATH,
    out_path: Path = DEFAULT_OUT_PATH,
    category_limits: dict[str, int] | None = None,
) -> dict[str, int]:
    pois = _load_pois(sqlite_path)
    limits = category_limits or CATEGORY_LIMITS
    selected = _select_by_category(pois, limits)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [_ugc_row(poi, index) for index, poi in enumerate(selected, start=1)]
    out_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    by_category: dict[str, int] = defaultdict(int)
    for poi in selected:
        by_category[str(poi["category"])] += 1
    return {"rows": len(rows), **{f"category_{key}": value for key, value in sorted(by_category.items())}}


def _load_pois(sqlite_path: Path) -> list[dict[str, Any]]:
    if not sqlite_path.exists():
        raise FileNotFoundError(f"POI sqlite not found: {sqlite_path}")
    with sqlite3.connect(sqlite_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, name, city, category, sub_category, district, business_area,
                   rating, price_per_person, review_count, queue_estimate_json,
                   tags_json, high_freq_keywords_json
            FROM app_pois
            WHERE city = 'hefei'
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _select_by_category(pois: list[dict[str, Any]], limits: dict[str, int]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for poi in pois:
        category = str(poi.get("category") or "")
        if category in limits:
            grouped[category].append(poi)
    selected: list[dict[str, Any]] = []
    for category, limit in limits.items():
        ranked = sorted(
            grouped.get(category, []),
            key=lambda poi: (
                -float(poi.get("rating") or 0),
                -int(poi.get("review_count") or 0),
                str(poi.get("id") or ""),
            ),
        )
        selected.extend(ranked[:limit])
    return selected


def _ugc_row(poi: dict[str, Any], index: int) -> dict[str, Any]:
    category = str(poi.get("category") or "restaurant")
    queue = _queue_minutes(poi)
    district = str(poi.get("district") or poi.get("business_area") or "合肥")
    sub_category = str(poi.get("sub_category") or CATEGORY_TITLES.get(category, "本地体验"))
    name = str(poi.get("name") or poi.get("id"))
    tags = _tags(poi, category, sub_category, district, queue)
    return {
        "poi_id": str(poi.get("id")),
        "poi_name": name,
        "city": "hefei",
        "category": category,
        "sub_category": sub_category,
        "district": district,
        "poi_rating": _rating(poi),
        "price_per_person": poi.get("price_per_person"),
        "source": "simulated_ugc",
        "tags": tags,
        "reviews": [
            {
                "post_id": f"demo_ugc_{index:04d}_01",
                "author": f"合肥本地体验官{index:03d}",
                "rating": min(5.0, round(_rating(poi) + 0.1, 1)),
                "content": _content_primary(name, category, sub_category, district, queue),
            },
            {
                "post_id": f"demo_ugc_{index:04d}_02",
                "author": f"周末路线记录员{index:03d}",
                "rating": _rating(poi),
                "content": _content_secondary(name, category, queue),
            },
        ],
    }


def _content_primary(name: str, category: str, sub_category: str, district: str, queue: int) -> str:
    if category == "restaurant":
        return f"{name}适合临时吃一顿{sub_category}，位置在{district}，人均和排队压力都比较适合半日路线，周末预估排队约{queue}分钟。"
    if category == "cafe":
        return f"{name}适合中途休息和整理路线，环境相对稳定，雨天或炎热时可以作为缓冲点，排队约{queue}分钟。"
    if category in {"culture", "shopping", "entertainment"}:
        return f"{name}适合天气不稳定时安排，室内停留更可控，也方便和餐饮点串联，排队约{queue}分钟。"
    if category == "nightlife":
        return f"{name}适合作为晚间收尾点，路线节奏不会太赶，适合朋友小聚，排队约{queue}分钟。"
    return f"{name}适合顺路打卡和散步，拍照属性较强，建议避开高温或大雨时段，排队约{queue}分钟。"


def _content_secondary(name: str, category: str, queue: int) -> str:
    if queue <= 20:
        queue_text = "排队压力低，适合说走就走"
    elif queue <= 40:
        queue_text = "热门时段可能等一会儿，适合作为可替换节点"
    else:
        queue_text = "高峰排队偏久，建议 Agent 根据时间窗谨慎安排"
    indoor_text = "室内体验更稳" if category in INDOOR_CATEGORIES else "天气好时体验更好"
    return f"{name}{queue_text}，{indoor_text}，和合肥本地半日游路线的兼容度较高。"


def _tags(poi: dict[str, Any], category: str, sub_category: str, district: str, queue: int) -> list[str]:
    tags = [category, sub_category, district, "合肥", "演示UGC"]
    if queue <= 25:
        tags.append("低排队")
    if category in INDOOR_CATEGORIES:
        tags.append("雨天友好")
    if category in {"scenic", "outdoor", "cafe"}:
        tags.append("拍照")
    for raw_key in ("tags_json", "high_freq_keywords_json"):
        for item in _json_list(poi.get(raw_key)):
            if isinstance(item, dict):
                value = str(item.get("keyword") or "")
            else:
                value = str(item)
            if value:
                tags.append(value)
    return list(dict.fromkeys(tags))[:10]


def _json_list(value: Any) -> list[Any]:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _queue_minutes(poi: dict[str, Any]) -> int:
    raw = poi.get("queue_estimate_json")
    try:
        parsed = json.loads(str(raw or "{}"))
    except json.JSONDecodeError:
        parsed = {}
    return int(parsed.get("weekend_peak") or parsed.get("weekday_peak") or 25)


def _rating(poi: dict[str, Any]) -> float:
    return round(float(poi.get("rating") or 4.2), 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic demo UGC for Hefei POIs.")
    parser.add_argument("--sqlite-path", type=Path, default=DEFAULT_SQLITE_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_PATH)
    args = parser.parse_args()
    stats = generate_demo_ugc(sqlite_path=args.sqlite_path, out_path=args.out)
    print(json.dumps(stats, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

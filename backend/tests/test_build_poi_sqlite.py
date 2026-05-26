import json
import sqlite3
from pathlib import Path


class FakeGeocoder:
    def geocode(self, row):
        locations = {
            "hf_scenic_poi_000001": (31.8781, 117.2764),
            "hf_shopping_poi_000001": (31.8352, 117.2273),
        }
        return locations.get(row["poi_id"])


def _write_jsonl(path: Path) -> None:
    rows = [
        {
            "poi_id": "hf_poi_000001",
            "poi_name": "庐州徽菜馆",
            "sub_category": "安徽菜(徽菜)",
            "district": "庐阳区",
            "poi_rating": 4.6,
            "price_per_person": 88,
            "reviews": [{"rating": 4.8, "content": "徽菜地道，适合朋友聚餐。"}],
        },
        {
            "poi_id": "hf_poi_000002",
            "poi_name": "重合咖啡馆",
            "sub_category": "咖啡厅",
            "district": "蜀山区",
            "poi_rating": 4.7,
            "price_per_person": 42,
            "reviews": [{"rating": 4.5, "content": "咖啡安静，适合休息拍照。"}],
        },
        {
            "poi_id": "hf_scenic_poi_000001",
            "poi_name": "杏花公园",
            "sub_category": "公园",
            "district": "庐阳区",
            "poi_rating": 4.9,
            "price_per_person": None,
            "reviews": [{"rating": 4.8, "content": "散步拍照都舒服。"}],
        },
        {
            "poi_id": "hf_shopping_poi_000001",
            "poi_name": "万象城",
            "sub_category": "购物中心",
            "district": "蜀山区",
            "poi_rating": 4.5,
            "price_per_person": None,
            "reviews": [{"rating": 4.3, "content": "商场好逛，吃喝方便。"}],
        },
    ]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
        encoding="utf-8",
    )


def test_build_sqlite_uses_same_poi_ids_across_core_tables(tmp_path):
    from scripts.build_poi_sqlite import build_sqlite

    source = tmp_path / "ugc_hefei.jsonl"
    out = tmp_path / "hefei_pois.sqlite"
    _write_jsonl(source)

    stats = build_sqlite(
        city="hefei",
        source=source,
        out=out,
        geocoder=FakeGeocoder(),
        reset=True,
    )

    assert stats["app_pois"] == 4
    assert stats["geocoded"] == 2

    con = sqlite3.connect(out)
    try:
        app_ids = {row[0] for row in con.execute("select id from app_pois")}
        feature_ids = {row[0] for row in con.execute("select poi_id from poi_feature_index")}
        evidence_ids = {row[0] for row in con.execute("select distinct poi_id from ugc_evidence_index")}
        categories = {
            row[0]: row[1]
            for row in con.execute("select category, count(*) from app_pois group by category")
        }
    finally:
        con.close()

    assert app_ids == feature_ids == evidence_ids
    assert categories == {"cafe": 1, "restaurant": 1, "scenic": 1, "shopping": 1}


def test_build_sqlite_records_import_metadata(tmp_path):
    from scripts.build_poi_sqlite import build_sqlite

    source = tmp_path / "ugc_hefei.jsonl"
    out = tmp_path / "hefei_pois.sqlite"
    _write_jsonl(source)

    build_sqlite(city="hefei", source=source, out=out, geocoder=FakeGeocoder(), reset=True)

    con = sqlite3.connect(out)
    try:
        meta = dict(con.execute("select key, value from import_meta"))
    finally:
        con.close()

    assert meta["city"] == "hefei"
    assert meta["coordinate_runtime"] == "amap_or_district_estimate"
    assert int(meta["app_pois"]) == 4

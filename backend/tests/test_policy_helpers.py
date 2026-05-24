from app.services.category_policy import categories_for_groups, normalize_category
from app.services.location_context import distance_from_origin, origin_from_query, within_radius


def test_category_policy_normalizes_non_food_categories():
    assert normalize_category("restaurant", "咖啡厅", ["咖啡", "低排队"]) == "cafe"
    assert normalize_category("restaurant", "公园", ["景点", "拍照"]) == "outdoor"
    assert normalize_category("restaurant", "展览馆", ["文艺", "雨天友好"]) == "culture"
    assert normalize_category("restaurant", "徽菜", ["安徽菜"]) == "restaurant"


def test_category_policy_expands_groups_without_duplicates():
    categories = categories_for_groups(["meal", "experience", "meal"])

    assert categories[:2] == ["restaurant", "cafe"]
    assert "scenic" in categories
    assert len(categories) == len(set(categories))


class _Query:
    origin_latitude = 31.82
    origin_longitude = 117.29
    radius_meters = 5000


class _Poi:
    latitude = 31.821
    longitude = 117.291


def test_location_context_resolves_origin_distance_and_radius():
    origin = origin_from_query(_Query())

    assert origin == (31.82, 117.29)
    assert distance_from_origin(_Poi(), origin) is not None
    assert within_radius(_Poi(), origin, _Query.radius_meters) is True

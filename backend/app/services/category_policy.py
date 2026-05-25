from collections.abc import Iterable


CATEGORY_NAMES = {
    "restaurant": "好好吃饭",
    "cafe": "咖啡休息",
    "scenic": "顺路打卡",
    "culture": "文艺展览",
    "shopping": "潮流逛街",
    "outdoor": "松弛散步",
    "entertainment": "玩乐现场",
    "nightlife": "夜色氛围",
}

CATEGORY_ORDER = [
    "restaurant",
    "culture",
    "scenic",
    "cafe",
    "entertainment",
    "nightlife",
    "shopping",
    "outdoor",
]

CANONICAL_CATEGORIES = tuple(CATEGORY_NAMES.keys())
MEAL_CATEGORIES = {"restaurant", "cafe"}
RESTAURANT_CATEGORIES = {"restaurant"}
EXPERIENCE_CATEGORIES = {"culture", "scenic", "entertainment", "nightlife", "shopping", "outdoor"}
SHOPPING_CATEGORIES = {"shopping"}
CORE_RECOMMENDATION_CATEGORIES = {"restaurant", "cafe", *EXPERIENCE_CATEGORIES}
ROUTE_ANCHOR_CATEGORIES = {"restaurant", *EXPERIENCE_CATEGORIES}

CATEGORY_GROUPS = {
    "meal": ["restaurant", "cafe"],
    "experience": ["culture", "scenic", "entertainment", "nightlife", "shopping", "outdoor"],
}


def category_label(category: str) -> str:
    return CATEGORY_NAMES.get(category, category)


def categories_for_groups(groups: Iterable[str]) -> list[str]:
    categories: list[str] = []
    for group in groups:
        categories.extend(CATEGORY_GROUPS.get(group, []))
    return list(dict.fromkeys(categories))


def normalize_category(
    category: str | None,
    sub_category: str | None,
    tags: Iterable[str],
    *,
    derived_category: str | None = None,
) -> str:
    derived = (derived_category or "").strip()
    if derived in CANONICAL_CATEGORIES:
        return derived

    normalized = (category or "").strip()
    if normalized in CANONICAL_CATEGORIES and normalized != "restaurant":
        return normalized

    text = " ".join(item for item in [category or "", sub_category or "", *tags] if item)
    if _contains_any(text, ["咖啡", "冷饮", "甜品", "糕点", "糕饼", "茶餐厅", "奶茶"]):
        return "cafe"
    if _contains_any(text, ["茶艺", "茶馆", "文艺", "展览", "美术馆", "博物馆", "雨天友好"]):
        return "culture"
    if _contains_any(text, ["酒吧", "小酒馆", "夜宵", "夜景"]):
        return "nightlife"
    if _contains_any(text, ["购物", "商场", "商业街", "购物中心", "百货", "步行街"]):
        return "shopping"
    if _contains_any(text, ["KTV", "电影院", "影院", "密室", "桌游", "剧场", "娱乐"]):
        return "entertainment"
    if _contains_any(text, ["公园", "户外", "绿地", "步道", "散步", "湿地"]):
        return "outdoor"
    if _contains_any(text, ["景点", "风景名胜", "旅游", "寺庙", "教堂", "祠堂", "广场"]):
        return "scenic"
    if _contains_any(text, ["餐饮", "餐厅", "中餐", "徽菜", "火锅", "快餐", "小吃", "烧烤", "海鲜"]):
        return "restaurant"
    return "restaurant"


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    return any(keyword in text for keyword in keywords)

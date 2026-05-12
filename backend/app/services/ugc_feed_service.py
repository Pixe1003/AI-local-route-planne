from app.repositories.poi_repo import get_poi_repository
from app.schemas.ugc import UgcFeedItem


class UgcFeedService:
    SOURCE_BY_INDEX = ["xiaohongshu", "dianping", "meituan"]

    TITLE_BY_CATEGORY = {
        "restaurant": "今晚这家本地菜很稳",
        "cafe": "适合中途休息的咖啡点",
        "scenic": "顺路拍照不绕路",
        "culture": "雨天也能逛的文艺点",
        "shopping": "边逛边歇的街区选择",
        "outdoor": "轻松散步的低成本选择",
        "entertainment": "朋友聚会可以加一站",
        "nightlife": "收尾看夜景很合适",
    }

    def __init__(self) -> None:
        self.repo = get_poi_repository()

    def list_feed(self, city: str = "hefei", limit: int = 24) -> list[UgcFeedItem]:
        pois = self.repo.list_by_city(city)
        if not pois and city != "hefei":
            pois = self.repo.list_by_city("hefei")
        cards: list[UgcFeedItem] = []
        for index, poi in enumerate(pois[:limit]):
            quote = poi.highlight_quotes[0].quote if poi.highlight_quotes else f"{poi.name}体验稳定。"
            cards.append(
                UgcFeedItem(
                    post_id=f"ugc_{poi.id}",
                    poi_id=poi.id,
                    poi_name=poi.name,
                    title=self.TITLE_BY_CATEGORY.get(poi.category, "值得收藏的本地 POI"),
                    source=self.SOURCE_BY_INDEX[index % len(self.SOURCE_BY_INDEX)],
                    author=f"本地体验官{index + 1:02d}",
                    cover_image=poi.cover_image,
                    quote=quote,
                    tags=list(dict.fromkeys(poi.tags + [item["keyword"] for item in poi.high_freq_keywords[:2]])),
                    category=poi.category,
                    rating=poi.rating,
                    price_per_person=poi.price_per_person,
                    estimated_queue_min=poi.queue_estimate.get("weekend_peak"),
                    city=poi.city,
                )
            )
        return cards

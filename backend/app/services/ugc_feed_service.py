from app.repositories.poi_repo import get_poi_repository
from app.repositories.ugc_vector_repo import UgcVectorRepo, get_ugc_vector_repo
from app.schemas.ugc import UgcFeedItem, UgcReview


class UgcFeedService:
    SOURCE_BY_INDEX = ["xiaohongshu", "dianping", "meituan"]
    DINING_CATEGORIES = {"restaurant", "cafe"}
    EXPERIENCE_CATEGORIES = {"scenic", "culture", "outdoor", "entertainment", "nightlife"}
    SHOPPING_CATEGORIES = {"shopping"}

    TITLE_BY_CATEGORY = {
        "restaurant": "本地餐饮真实体验",
        "cafe": "适合中途休息的咖啡点",
        "scenic": "顺路拍照不绕路",
        "culture": "雨天也能逛的文艺点",
        "shopping": "边逛边歇的街区选择",
        "outdoor": "轻松散步的低成本选择",
        "entertainment": "朋友聚会可以加一站",
        "nightlife": "收尾看夜景很合适",
    }

    def __init__(self, ugc_repo: UgcVectorRepo | None = None) -> None:
        self.repo = get_poi_repository()
        self.ugc_repo = ugc_repo or get_ugc_vector_repo()

    def list_feed(self, city: str = "hefei", limit: int = 24) -> list[UgcFeedItem]:
        ugc_cards = self._list_ugc_cards(city=city, limit=limit)
        if ugc_cards:
            return ugc_cards

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

    def _list_ugc_cards(self, *, city: str, limit: int) -> list[UgcFeedItem]:
        reviews = self.ugc_repo.list_reviews(city=city)
        if not reviews:
            return []
        selected = self._balanced_reviews(reviews, limit=limit)
        return [self._review_to_card(review, index) for index, review in enumerate(selected)]

    def _balanced_reviews(self, reviews: list[UgcReview], *, limit: int) -> list[UgcReview]:
        if limit <= 0:
            return []
        dining_target, experience_target, shopping_target = self._feed_targets(limit)
        selected: list[UgcReview] = []
        used_indexes: set[int] = set()

        self._take_reviews(
            reviews,
            selected,
            used_indexes,
            categories=self.DINING_CATEGORIES,
            count=dining_target,
        )
        self._take_reviews(
            reviews,
            selected,
            used_indexes,
            categories=self.EXPERIENCE_CATEGORIES,
            count=experience_target,
        )
        self._take_reviews(
            reviews,
            selected,
            used_indexes,
            categories=self.SHOPPING_CATEGORIES,
            count=shopping_target,
        )

        if len(selected) < limit:
            self._take_reviews(reviews, selected, used_indexes, categories=None, count=limit - len(selected))
        return selected[:limit]

    def _feed_targets(self, limit: int) -> tuple[int, int, int]:
        if limit <= 2:
            return limit, 0, 0
        dining = max(1, round(limit * 0.65))
        experience = max(1, round(limit * 0.22))
        shopping = max(0, limit - dining - experience)
        if limit >= 6:
            shopping = max(1, shopping)
        while dining + experience + shopping > limit:
            dining -= 1
        return dining, experience, shopping

    def _take_reviews(
        self,
        reviews: list[UgcReview],
        selected: list[UgcReview],
        used_indexes: set[int],
        *,
        categories: set[str] | None,
        count: int,
    ) -> None:
        if count <= 0:
            return
        added = 0
        for index, review in enumerate(reviews):
            if index in used_indexes:
                continue
            if categories is not None and review.category not in categories:
                continue
            selected.append(review)
            used_indexes.add(index)
            added += 1
            if added >= count:
                return

    def _review_to_card(self, review: UgcReview, index: int) -> UgcFeedItem:
        return UgcFeedItem(
            post_id=review.post_id,
            poi_id=review.poi_id,
            poi_name=review.poi_name,
            title=self.TITLE_BY_CATEGORY.get(review.category, "值得收藏的本地 POI"),
            source=review.source,
            author=review.author or f"本地体验官{index + 1:02d}",
            cover_image=None,
            quote=review.content,
            tags=review.tags[:6],
            category=review.category,
            rating=review.rating or review.poi_rating or 4.0,
            price_per_person=review.price_per_person,
            estimated_queue_min=None,
            city=review.city,
        )

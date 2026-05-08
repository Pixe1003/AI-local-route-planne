from datetime import datetime, timezone
from uuid import uuid4

from app.repositories.poi_repo import get_poi_repository
from app.repositories.vector_repo import VectorRepository
from app.schemas.pool import PoiInPool, PoolCategory, PoolMeta, PoolRequest, PoolResponse
from app.services.agent_skill_registry import get_agent_skill_registry
from app.services.poi_scoring_service import PoiScoringService
from app.services.state import POOL_REGISTRY


class PoolService:
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

    EXPERIENCE_CATEGORIES = {"culture", "scenic", "entertainment", "nightlife"}

    def __init__(self) -> None:
        self.agent_skill = get_agent_skill_registry().get_skill("recommend")
        self.repo = get_poi_repository()
        self.vector_repo = VectorRepository()
        self.poi_scorer = PoiScoringService()

    def generate_pool(self, request: PoolRequest) -> PoolResponse:
        profile = request.need_profile
        persona_tags = self._persona_tags(request)
        free_text = request.free_text or (profile.raw_query if profile else None)
        budget = (
            profile.budget.budget_per_person
            if profile and profile.budget.budget_per_person is not None
            else request.budget_per_person
        )
        city = profile.destination.city if profile else request.city
        candidates = self.repo.list_by_city(city)
        if not candidates and city != "shanghai":
            candidates = self.repo.list_by_city("shanghai")
        scored = sorted(
            (
                (
                    self._score_poi(
                        poi,
                        persona_tags,
                        free_text,
                        budget,
                        request=request,
                    ),
                    poi,
                )
                for poi in candidates
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        selected = scored[:24]
        grouped: dict[str, list[PoiInPool]] = {}
        for score, poi in selected:
            breakdown = self.poi_scorer.score_poi(
                poi,
                profile=profile,
                preference_snapshot=request.preference_snapshot,
                free_text=free_text,
            )
            grouped.setdefault(poi.category, []).append(
                PoiInPool(
                    id=poi.id,
                    name=poi.name,
                    category=poi.category,
                    rating=poi.rating,
                    price_per_person=poi.price_per_person,
                    cover_image=poi.cover_image,
                    distance_meters=None,
                    why_recommend=self._why_recommend(poi.name, poi.tags, free_text, breakdown.history_preference),
                    highlight_quote=poi.highlight_quotes[0].quote if poi.highlight_quotes else None,
                    keywords=[item["keyword"] for item in poi.high_freq_keywords[:5]],
                    estimated_queue_min=poi.queue_estimate["weekend_peak"],
                    suitable_score=round(score, 3),
                    score_breakdown=breakdown.model_dump(),
                )
            )
        categories = [
            PoolCategory(
                name=self.CATEGORY_NAMES.get(category, category),
                description=f"根据你的输入和收藏偏好，为你挑选的{self.CATEGORY_NAMES.get(category, category)}候选。",
                pois=grouped[category],
            )
            for category in self.CATEGORY_ORDER
            if category in grouped
        ]
        default_selected_ids = self._default_selected_ids(categories, request)
        response = PoolResponse(
            pool_id=f"pool_{uuid4().hex[:10]}",
            categories=categories,
            default_selected_ids=default_selected_ids,
            meta=PoolMeta(
                total_count=sum(len(category.pois) for category in categories),
                generated_at=datetime.now(timezone.utc),
                user_persona_summary=self._persona_summary(persona_tags, free_text, request),
            ),
        )
        POOL_REGISTRY[response.pool_id] = response
        return response

    def _score_poi(
        self,
        poi,
        persona_tags: list[str],
        free_text: str | None,
        budget_per_person: int | None,
        request: PoolRequest | None = None,
    ) -> float:
        breakdown = self.poi_scorer.score_poi(
            poi,
            profile=request.need_profile if request else None,
            preference_snapshot=request.preference_snapshot if request else None,
            free_text=free_text,
        )
        rating_score = poi.rating / 5 * 0.22
        semantic_score = self.vector_repo.score(poi, persona_tags, free_text) * 0.24
        popularity_score = min(poi.review_count / 1200, 1) * 0.08
        queue_bonus = max(0, (60 - poi.queue_estimate["weekend_peak"]) / 60) * 0.08
        profile_score = min(max(breakdown.total, 0) / 100, 1) * 0.24
        history_score = max(breakdown.history_preference, 0) / 22 * 0.20
        budget_penalty = 0.0
        if budget_per_person and poi.price_per_person and poi.price_per_person > budget_per_person:
            budget_penalty = min((poi.price_per_person - budget_per_person) / max(budget_per_person, 1), 2) * 0.18
        return max(
            0,
            min(
                1,
                rating_score
                + semantic_score
                + popularity_score
                + queue_bonus
                + profile_score
                + history_score
                - budget_penalty,
            ),
        )

    def _why_recommend(
        self,
        name: str,
        tags: list[str],
        free_text: str | None,
        history_preference: float,
    ) -> str:
        if history_preference >= 10:
            return f"{name}和你刚收藏的内容高度相似，适合作为本次即时路线的优先候选。"
        if free_text and "排队" in free_text and "低排队" in tags:
            return f"{name}排队压力较低，适合作为路线里的稳定点。"
        if "photogenic" in tags or "拍照" in tags:
            return f"{name}适合拍照打卡，也方便和周边点位串联。"
        return f"{name}和本次需求匹配度较高，适合作为路线候选。"

    def _default_selected_ids(self, categories: list[PoolCategory], request: PoolRequest) -> list[str]:
        all_pois = [poi for category in categories for poi in category.pois]
        by_id = {poi.id: poi for poi in all_pois}
        defaults: list[str] = []

        for poi_id in request.preference_snapshot.liked_poi_ids if request.preference_snapshot else []:
            poi = by_id.get(poi_id)
            if poi and self._reasonable_for_main_route(poi, request) and poi_id not in defaults:
                defaults.append(poi_id)

        self._append_best_category(defaults, all_pois, {"restaurant"}, request)
        self._append_best_category(defaults, all_pois, self.EXPERIENCE_CATEGORIES, request)
        for poi in sorted(all_pois, key=lambda item: item.suitable_score, reverse=True):
            if poi.id not in defaults and self._reasonable_for_main_route(poi, request):
                defaults.append(poi.id)
            if len(defaults) >= 5:
                break
        if len(defaults) < 3:
            for poi in sorted(all_pois, key=lambda item: item.suitable_score, reverse=True):
                if poi.id not in defaults:
                    defaults.append(poi.id)
                if len(defaults) >= 3:
                    break
        return defaults

    def _append_best_category(
        self,
        defaults: list[str],
        pois: list[PoiInPool],
        categories: set[str],
        request: PoolRequest,
    ) -> None:
        if any(poi.id in defaults and poi.category in categories for poi in pois):
            return
        options = [
            poi
            for poi in pois
            if poi.category in categories and self._reasonable_for_main_route(poi, request)
        ]
        if options:
            best = max(options, key=lambda item: item.suitable_score)
            if best.id not in defaults:
                defaults.append(best.id)

    def _reasonable_for_main_route(self, poi: PoiInPool, request: PoolRequest) -> bool:
        if request.budget_per_person and poi.price_per_person:
            if poi.price_per_person > request.budget_per_person:
                return False
        if "少排队" in (request.free_text or "") and (poi.estimated_queue_min or 0) > 45:
            return False
        return True

    def _persona_summary(
        self,
        persona_tags: list[str],
        free_text: str | None,
        request: PoolRequest,
    ) -> str:
        tags = "、".join(persona_tags)
        liked_count = len(request.preference_snapshot.liked_poi_ids) if request.preference_snapshot else 0
        if liked_count:
            return f"已参考 {liked_count} 个收藏 POI，并结合 {tags} 与当前输入生成即时候选池。"
        return f"本次按 {tags} 偏好生成，重点平衡体验、通勤和排队风险。"

    def _persona_tags(self, request: PoolRequest) -> list[str]:
        if request.persona_tags:
            return request.persona_tags
        profile = request.need_profile
        if not profile:
            return ["couple"]
        tags: list[str] = []
        if profile.party_type:
            tags.append(profile.party_type)
        if profile.food_preferences:
            tags.append("foodie")
        if any(item in {"拍照", "打卡"} for item in profile.activity_preferences):
            tags.append("photographer")
        if not tags:
            tags.append("couple")
        return tags

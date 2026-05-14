from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.repositories.poi_repo import get_poi_repository
from app.repositories.vector_repo import VectorRepository
from app.schemas.pool import PoiInPool, PoolCategory, PoolMeta, PoolRequest, PoolResponse
from app.services.agent_skill_registry import get_agent_skill_registry
from app.services.poi_scoring_service import PoiScoringService
from app.services.state import POOL_REGISTRY
from app.solver.distance import haversine_meters


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
        self.ugc_repo = self.poi_scorer.ugc_repo

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
        if not candidates and city != "hefei":
            candidates = self.repo.list_by_city("hefei")
        if request.user_facts and request.user_facts.rejected_poi_ids:
            rejected = set(request.user_facts.rejected_poi_ids)
            filtered = [poi for poi in candidates if poi.id not in rejected]
            if len(filtered) >= 3:
                candidates = filtered
        ugc_by_poi = self._ugc_hits_by_poi(request.ugc_hits)
        scored = sorted(
            (
                (
                    self._score_poi(
                        poi,
                        persona_tags,
                        free_text,
                        budget,
                        request=request,
                        ugc_by_poi=ugc_by_poi,
                    ),
                    poi,
                )
                for poi in candidates
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        selected = self._diverse_candidates(scored, limit=24)
        grouped: dict[str, list[PoiInPool]] = {}
        for score, poi in selected:
            breakdown = self.poi_scorer.score_poi(
                poi,
                profile=profile,
                preference_snapshot=request.preference_snapshot,
                free_text=free_text,
                user_facts=request.user_facts,
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
                    highlight_quote=self._highlight_quote(poi, free_text, request.ugc_hits),
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
        ugc_by_poi: dict[str, list[dict[str, Any]]] | None = None,
    ) -> float:
        rating_score = poi.rating / 5 * 0.22
        semantic_score = self.vector_repo.score(poi, persona_tags, free_text) * 0.24
        popularity_score = min(poi.review_count / 1200, 1) * 0.08
        queue_bonus = max(0, (60 - poi.queue_estimate["weekend_peak"]) / 60) * 0.08
        profile_score = self._cheap_profile_score(poi, request, free_text) * 0.24
        history_score = self._cheap_history_score(poi, request) * 0.20
        ugc_bonus = 0.10 if ugc_by_poi and poi.id in ugc_by_poi else 0.0
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
                + ugc_bonus
                - budget_penalty,
            ),
        )

    def _diverse_candidates(self, scored, *, limit: int):
        selected: list[tuple[float, object]] = []
        selected_ids: set[str] = set()

        for category in self.CATEGORY_ORDER:
            item = next((entry for entry in scored if entry[1].category == category), None)
            if item and item[1].id not in selected_ids:
                selected.append(item)
                selected_ids.add(item[1].id)

        for item in scored:
            if len(selected) >= limit:
                break
            if item[1].id in selected_ids:
                continue
            selected.append(item)
            selected_ids.add(item[1].id)
        return selected[:limit]

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

    def _highlight_quote(self, poi, free_text: str | None, ugc_hits: list[dict[str, Any]] | None = None) -> str | None:
        for hit in ugc_hits or []:
            if str(hit.get("poi_id")) == poi.id and hit.get("snippet"):
                return str(hit["snippet"])
        if ugc_hits:
            return poi.highlight_quotes[0].quote if poi.highlight_quotes else None
        hits = self.ugc_repo.evidence_for_poi(poi.id, free_text or "", top_k=1)
        if hits:
            return hits[0].snippet
        return poi.highlight_quotes[0].quote if poi.highlight_quotes else None

    def _cheap_profile_score(self, poi, request: PoolRequest | None, free_text: str | None) -> float:
        score = 0.45
        profile = request.need_profile if request else None
        text = free_text or ""
        if profile and profile.party_type and profile.party_type in poi.suitable_for:
            score += 0.12
        if any(keyword in text for keyword in ["吃", "餐", "美食", "本地菜", "火锅"]):
            score += 0.18 if poi.category == "restaurant" else 0.0
        if "咖啡" in text and poi.category == "cafe":
            score += 0.14
        if any(keyword in text for keyword in ["拍照", "打卡"]) and (
            "photogenic" in poi.tags or "拍照" in poi.tags or "打卡" in poi.tags
        ):
            score += 0.12
        return min(score, 1.0)

    def _cheap_history_score(self, poi, request: PoolRequest | None) -> float:
        if request is None:
            return 0.0
        score = 0.0
        snapshot = request.preference_snapshot
        if snapshot:
            if poi.id in snapshot.disliked_poi_ids:
                return -0.7
            if poi.id in snapshot.liked_poi_ids:
                score += 0.7
            score += snapshot.category_weights.get(poi.category, 0.0) * 0.2
        facts = request.user_facts
        if facts:
            if poi.id in facts.rejected_poi_ids:
                return -0.8
            if poi.category in facts.favorite_categories:
                score += 0.25
            if poi.category in facts.avoid_categories:
                score -= 0.35
        return max(-1.0, min(score, 1.0))

    def _ugc_hits_by_poi(self, ugc_hits: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for hit in ugc_hits:
            poi_id = str(hit.get("poi_id") or "")
            if poi_id:
                grouped.setdefault(poi_id, []).append(hit)
        return grouped

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
        return self._route_order_ids(defaults)

    def recommend_route_update(
        self,
        *,
        pool_id: str | None,
        current_poi_ids: list[str],
        feedback_text: str,
    ) -> tuple[list[str], list[str]]:
        pool = POOL_REGISTRY.get(pool_id or "")
        pool_pois = self._pool_pois(pool) if pool else []
        if not pool_pois:
            pool_pois = [
                PoiInPool(
                    id=poi.id,
                    name=poi.name,
                    category=poi.category,
                    rating=poi.rating,
                    price_per_person=poi.price_per_person,
                    cover_image=poi.cover_image,
                    distance_meters=None,
                    why_recommend="Based on the current route feedback.",
                    highlight_quote=self._highlight_quote(poi, feedback_text),
                    keywords=[item["keyword"] for item in poi.high_freq_keywords[:5]],
                    estimated_queue_min=poi.queue_estimate["weekend_peak"],
                    suitable_score=poi.rating / 5,
                    score_breakdown={},
                )
                for poi in self.repo.list_by_city("hefei")
            ]
        by_id = {poi.id: poi for poi in pool_pois}
        avoid_categories = self._feedback_avoid_categories(feedback_text)
        avoid_queue = self._feedback_avoid_queue(feedback_text)

        def allowed(poi: PoiInPool) -> bool:
            if poi.category in avoid_categories:
                return False
            return not (avoid_queue and (poi.estimated_queue_min or 0) > 45)

        selected: list[str] = []
        for poi_id in current_poi_ids:
            poi = by_id.get(poi_id)
            if poi and allowed(poi) and poi_id not in selected:
                selected.append(poi_id)
        for poi in sorted(pool_pois, key=lambda item: item.suitable_score, reverse=True):
            if allowed(poi) and poi.id not in selected:
                selected.append(poi.id)
            if len(selected) >= 5:
                break

        selected = self._ensure_route_mix(selected, pool_pois, allowed)
        selected = self._route_order_ids(selected[:5])
        alternatives = [
            poi.id
            for poi in sorted(pool_pois, key=lambda item: item.suitable_score, reverse=True)
            if poi.id not in selected and allowed(poi)
        ][:8]
        return selected, alternatives

    def _pool_pois(self, pool: PoolResponse | None) -> list[PoiInPool]:
        if pool is None:
            return []
        return [poi for category in pool.categories for poi in category.pois]

    def _feedback_avoid_categories(self, feedback_text: str) -> set[str]:
        if any(keyword in feedback_text for keyword in ["不要商场", "不去商场", "别去商场", "少逛街"]):
            return {"shopping"}
        return set()

    def _feedback_avoid_queue(self, feedback_text: str) -> bool:
        return any(keyword in feedback_text for keyword in ["少排队", "不排队", "排队少", "别排队"])

    def _ensure_route_mix(
        self,
        selected_ids: list[str],
        pool_pois: list[PoiInPool],
        allowed,
    ) -> list[str]:
        next_ids = list(dict.fromkeys(selected_ids))
        by_id = {poi.id: poi for poi in pool_pois}
        categories = {by_id[poi_id].category for poi_id in next_ids if poi_id in by_id}
        if "restaurant" not in categories:
            self._replace_or_append_best_pool_category(next_ids, pool_pois, {"restaurant"}, allowed)
        categories = {by_id[poi_id].category for poi_id in next_ids if poi_id in by_id}
        if not categories & self.EXPERIENCE_CATEGORIES:
            self._replace_or_append_best_pool_category(next_ids, pool_pois, self.EXPERIENCE_CATEGORIES, allowed)
        return next_ids

    def _replace_or_append_best_pool_category(
        self,
        selected_ids: list[str],
        pool_pois: list[PoiInPool],
        categories: set[str],
        allowed,
    ) -> None:
        replacement = next(
            (
                poi
                for poi in sorted(pool_pois, key=lambda item: item.suitable_score, reverse=True)
                if poi.category in categories and allowed(poi) and poi.id not in selected_ids
            ),
            None,
        )
        if replacement is None:
            return
        by_id = {poi.id: poi for poi in pool_pois}
        for index in range(len(selected_ids) - 1, -1, -1):
            selected = by_id.get(selected_ids[index])
            if selected and selected.category not in {"restaurant", *self.EXPERIENCE_CATEGORIES}:
                selected_ids[index] = replacement.id
                return
        selected_ids.append(replacement.id)

    def _route_order_ids(self, poi_ids: list[str]) -> list[str]:
        ids = list(dict.fromkeys(poi_ids))
        if len(ids) < 3:
            return ids
        pois = self.repo.get_many(ids)
        by_id = {poi.id: poi for poi in pois}
        ordered_ids = [ids[0]]
        remaining = [poi_id for poi_id in ids[1:] if poi_id in by_id]
        while remaining:
            current = by_id[ordered_ids[-1]]
            next_id = min(remaining, key=lambda poi_id: haversine_meters(current, by_id[poi_id]))
            ordered_ids.append(next_id)
            remaining.remove(next_id)
        return ordered_ids

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

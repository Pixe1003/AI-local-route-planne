from datetime import datetime, timezone
from uuid import uuid4

from app.repositories.poi_repo import get_poi_repository
from app.repositories.poi_repo import PoiRepository
from app.repositories.vector_repo import VectorRepository
from app.schemas.pool import PoiInPool, PoolCategory, PoolMeta, PoolRequest, PoolResponse
from app.schemas.rag import RetrievalQuery, RetrievedPoi
from app.services.agent_skill_registry import get_agent_skill_registry
from app.services.category_policy import (
    CATEGORY_ORDER,
    CORE_RECOMMENDATION_CATEGORIES,
    EXPERIENCE_CATEGORIES,
    RESTAURANT_CATEGORIES,
    category_label,
)
from app.services.location_context import (
    distance_from_origin,
    origin_from_request,
    plan_context_from_pool_request,
)
from app.services.poi_scoring_service import PoiScoringService
from app.services.retrieval_service import RetrievalService
from app.services.state import POOL_REGISTRY


class PoolService:
    def __init__(
        self,
        repo: PoiRepository | None = None,
        retrieval_service: RetrievalService | None = None,
    ) -> None:
        self.agent_skill = get_agent_skill_registry().get_skill("recommend")
        self.repo = repo or get_poi_repository()
        self.vector_repo = VectorRepository()
        self.poi_scorer = PoiScoringService()
        self.retrieval_service = retrieval_service or RetrievalService(repo=self.repo)

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
        retrieved = self._retrieve_candidates(request, city, persona_tags, free_text, budget)
        retrieved_by_id = {item.poi_id: item for item in retrieved}
        candidates = self._candidate_pois(city, retrieved, request)
        data_warning = "city_data_unavailable" if not candidates else None
        origin = origin_from_request(request)
        scoring_context = plan_context_from_pool_request(request, city)
        scored = sorted(
            (
                (
                    self._score_poi(
                        poi,
                        persona_tags,
                        free_text,
                        budget,
                        request=request,
                        retrieval_score=(
                            retrieved_by_id[poi.id].score if poi.id in retrieved_by_id else None
                        ),
                        origin=origin,
                        context=scoring_context,
                    ),
                    poi,
                )
                for poi in candidates
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        selected = self._diverse_selection(scored, limit=24)
        grouped: dict[str, list[PoiInPool]] = {}
        for score, poi in selected:
            retrieved_item = retrieved_by_id.get(poi.id)
            evidence = retrieved_item.evidence_snippets if retrieved_item else []
            breakdown = self.poi_scorer.score_poi(
                poi,
                profile=profile,
                context=scoring_context,
                preference_snapshot=request.preference_snapshot,
                free_text=free_text,
            )
            highlight_quote = (
                evidence[0].text
                if evidence
                else poi.highlight_quotes[0].quote if poi.highlight_quotes else None
            )
            grouped.setdefault(poi.category, []).append(
                PoiInPool(
                    id=poi.id,
                    name=poi.name,
                    category=poi.category,
                    rating=poi.rating,
                    price_per_person=poi.price_per_person,
                    cover_image=poi.cover_image,
                    distance_meters=distance_from_origin(poi, origin),
                    why_recommend=self._why_recommend(
                        poi.name,
                        poi.tags,
                        free_text,
                        breakdown.history_preference,
                        retrieved_item,
                    ),
                    highlight_quote=highlight_quote,
                    keywords=[item["keyword"] for item in poi.high_freq_keywords[:5]],
                    estimated_queue_min=poi.queue_estimate["weekend_peak"],
                    suitable_score=round(score, 3),
                    score_breakdown=breakdown.model_dump(),
                    retrieval_score=retrieved_item.score if retrieved_item else None,
                    retrieval_provenance=retrieved_item.provenance if retrieved_item else [],
                    evidence_snippets=evidence,
                )
            )
        categories = [
            PoolCategory(
                name=category_label(category),
                description=f"根据你的输入和收藏偏好，为你挑选的{category_label(category)}候选。",
                pois=grouped[category],
            )
            for category in CATEGORY_ORDER
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
                data_warning=data_warning,
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
        retrieval_score: float | None = None,
        origin: tuple[float, float] | None = None,
        context=None,
    ) -> float:
        breakdown = self.poi_scorer.score_poi(
            poi,
            context=context,
            profile=request.need_profile if request else None,
            preference_snapshot=request.preference_snapshot if request else None,
            free_text=free_text,
        )
        rating_score = poi.rating / 5 * 0.22
        semantic_score = (
            retrieval_score if retrieval_score is not None else self.vector_repo.score(poi, persona_tags, free_text)
        ) * 0.24
        popularity_score = min(poi.review_count / 1200, 1) * 0.08
        queue_bonus = max(0, (60 - poi.queue_estimate["weekend_peak"]) / 60) * 0.08
        profile_score = min(max(breakdown.total, 0) / 100, 1) * 0.24
        history_score = max(breakdown.history_preference, 0) / 22 * 0.20
        budget_penalty = 0.0
        if budget_per_person and poi.price_per_person and poi.price_per_person > budget_per_person:
            budget_penalty = min((poi.price_per_person - budget_per_person) / max(budget_per_person, 1), 2) * 0.18
        distance_penalty = 0.0
        if origin:
            distance = distance_from_origin(poi, origin)
            if distance is not None:
                distance_penalty = min(max(0, distance - 1500) / 1000 * 0.02, 0.18)
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
                - budget_penalty
                - distance_penalty,
            ),
        )

    def _why_recommend(
        self,
        name: str,
        tags: list[str],
        free_text: str | None,
        history_preference: float,
        retrieved_item: RetrievedPoi | None = None,
    ) -> str:
        if retrieved_item and retrieved_item.evidence_snippets:
            if any(item.source_type == "ugc_review" for item in retrieved_item.evidence_snippets):
                return f"{name}由本次 UGC 语义检索召回，证据和你的细粒度需求更贴近。"
            return f"{name}由本次语义检索召回，证据来自真实 POI 资料和高频关键词。"
        if history_preference >= 10:
            return f"{name}和你刚收藏的内容高度相似，适合作为本次即时路线的优先候选。"
        if free_text and "排队" in free_text and "低排队" in tags:
            return f"{name}排队压力较低，适合作为路线里的稳定点。"
        if "photogenic" in tags or "拍照" in tags:
            return f"{name}适合拍照打卡，也方便和周边点位串联。"
        return f"{name}和本次需求匹配度较高，适合作为路线候选。"

    def _retrieve_candidates(
        self,
        request: PoolRequest,
        city: str,
        persona_tags: list[str],
        free_text: str | None,
        budget: int | None,
    ) -> list[RetrievedPoi]:
        terms = [*persona_tags]
        if request.preference_snapshot:
            terms.extend(list(request.preference_snapshot.category_weights)[:6])
            terms.extend(list(request.preference_snapshot.tag_weights)[:8])
            terms.extend(list(request.preference_snapshot.keyword_weights)[:8])
        profile = request.need_profile
        if profile:
            terms.extend(profile.activity_preferences)
            terms.extend(profile.food_preferences)
            terms.extend(profile.route_style)
        base = dict(
            city=city,
            text=free_text,
            top_k=80,
            budget_per_person=budget,
            avoid_queue="少排队" in (free_text or ""),
            preference_terms=list(dict.fromkeys(terms)),
            origin_latitude=request.origin_latitude,
            origin_longitude=request.origin_longitude,
            radius_meters=request.radius_meters,
        )
        profile_results = self.retrieval_service.retrieve(
            RetrievalQuery(**base, source_types=["poi_profile"])
        )
        ugc_results = self.retrieval_service.retrieve(
            RetrievalQuery(**base, source_types=["ugc_review"])
        )
        feature_results = self._feature_bucket_candidates(city, persona_tags, free_text, budget)
        return self._merge_retrieved([profile_results, ugc_results, feature_results])[:80]

    def _candidate_pois(
        self,
        city: str,
        retrieved: list[RetrievedPoi],
        request: PoolRequest,
    ):
        ids: list[str] = []
        ids.extend(item.poi_id for item in retrieved)
        if request.preference_snapshot:
            ids.extend(request.preference_snapshot.liked_poi_ids)
        pois = self.repo.get_many(list(dict.fromkeys(ids)))
        city_pois = self.repo.list_by_city(city, limit=500)
        existing = {poi.id for poi in pois}
        supplements = sorted(
            (poi for poi in city_pois if poi.id not in existing),
            key=lambda poi: (
                poi.category not in CORE_RECOMMENDATION_CATEGORIES,
                poi.queue_estimate["weekend_peak"],
                -(poi.rating or 0),
                -(poi.review_count or 0),
            ),
        )
        for poi in supplements[:160]:
            pois.append(poi)
        return pois

    def _merge_retrieved(self, groups: list[list[RetrievedPoi]]) -> list[RetrievedPoi]:
        merged: dict[str, RetrievedPoi] = {}
        for group in groups:
            for item in group:
                existing = merged.get(item.poi_id)
                if existing is None:
                    merged[item.poi_id] = item.model_copy(deep=True)
                    continue
                existing.score = max(existing.score, item.score)
                existing.evidence_snippets = sorted(
                    [*existing.evidence_snippets, *item.evidence_snippets],
                    key=lambda snippet: snippet.score,
                    reverse=True,
                )[:4]
                existing.provenance = list(dict.fromkeys([*existing.provenance, *item.provenance]))
        return sorted(merged.values(), key=lambda item: item.score, reverse=True)

    def _feature_bucket_candidates(
        self,
        city: str,
        persona_tags: list[str],
        free_text: str | None,
        budget: int | None,
    ) -> list[RetrievedPoi]:
        from app.schemas.rag import EvidenceSnippet

        candidates = self.repo.list_by_city(city, limit=500)
        scored: list[tuple[float, object]] = []
        for poi in candidates:
            if budget and poi.price_per_person and poi.price_per_person > budget * 1.5:
                continue
            semantic = self.vector_repo.score(poi, persona_tags, free_text)
            quality = min((poi.rating or 0) / 5, 1.0) * 0.35
            low_queue = max(0, (60 - poi.queue_estimate["weekend_peak"]) / 60) * 0.2
            category_bonus = 0.12 if poi.category in CORE_RECOMMENDATION_CATEGORIES else 0
            score = min(1.0, semantic + quality + low_queue + category_bonus)
            scored.append((score, poi))
        results: list[RetrievedPoi] = []
        for score, poi in sorted(scored, key=lambda item: item[0], reverse=True)[:40]:
            text = " ".join(
                [
                    poi.name,
                    poi.category,
                    poi.sub_category or "",
                    " ".join(poi.tags[:6]),
                    " ".join(str(item.get("keyword", "")) for item in poi.high_freq_keywords[:4]),
                ]
            )
            results.append(
                RetrievedPoi(
                    poi_id=poi.id,
                    score=round(score, 4),
                    evidence_snippets=[
                        EvidenceSnippet(
                            doc_id=f"feature_bucket:{poi.id}",
                            source_type="feature_bucket",
                            text=text,
                            score=round(score, 4),
                        )
                    ],
                    provenance=["feature_bucket"],
                )
            )
        return results

    def _diverse_selection(self, scored, limit: int):
        selected = []
        selected_ids: set[str] = set()
        for category in CATEGORY_ORDER:
            category_items = [item for item in scored if item[1].category == category]
            quota = 2 if category in CORE_RECOMMENDATION_CATEGORIES else 1
            for item in category_items[:quota]:
                if item[1].id in selected_ids:
                    continue
                selected.append(item)
                selected_ids.add(item[1].id)
                if len(selected) >= limit:
                    return selected
        for item in scored:
            if item[1].id in selected_ids:
                continue
            selected.append(item)
            selected_ids.add(item[1].id)
            if len(selected) >= limit:
                break
        return selected

    def _default_selected_ids(self, categories: list[PoolCategory], request: PoolRequest) -> list[str]:
        all_pois = [poi for category in categories for poi in category.pois]
        by_id = {poi.id: poi for poi in all_pois}
        defaults: list[str] = []

        for poi_id in request.preference_snapshot.liked_poi_ids if request.preference_snapshot else []:
            poi = by_id.get(poi_id)
            if poi and self._reasonable_for_main_route(poi, request) and poi_id not in defaults:
                defaults.append(poi_id)

        self._append_best_category(defaults, all_pois, RESTAURANT_CATEGORIES, request)
        self._append_best_category(defaults, all_pois, EXPERIENCE_CATEGORIES, request)
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

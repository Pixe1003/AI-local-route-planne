from datetime import datetime, timezone
import logging
import queue
import threading
import time
from typing import Any, Callable
from uuid import uuid4

from app.config import get_settings
from app.repositories.poi_repo import get_poi_repository
from app.repositories.poi_repo import PoiRepository
from app.repositories.vector_repo import VectorRepository
from app.schemas.poi import PoiDetail
from app.schemas.pool import PoiInPool, PoolCategory, PoolMeta, PoolRequest, PoolResponse
from app.schemas.rag import RetrievalQuery, RetrievedPoi
from app.services.agent_skill_registry import get_agent_skill_registry
from app.services.location_context import (
    distance_from_origin,
    origin_from_context,
    origin_from_request,
    plan_context_from_pool_request,
    radius_from_request,
    within_radius,
)
from app.services.poi_retrieval_service import PoiRetrievalService
from app.services.poi_scoring_service import PoiScoringService
from app.services.retrieval_service import RetrievalService
from app.services.state import POOL_REGISTRY
from app.solver.distance import haversine_meters


_MISSING = object()
_SEMANTIC_LOGGER_NAMES = ("huggingface_hub", "sentence_transformers")


class SemanticRetrievalGuard:
    _cooldown_until: float = 0.0

    @classmethod
    def reset_cooldown(cls) -> None:
        cls._cooldown_until = 0.0

    @classmethod
    def run(
        cls,
        task: Callable[[], list[RetrievedPoi]],
        *,
        timeout_ms: int,
        cooldown_seconds: int,
    ) -> tuple[list[RetrievedPoi], dict[str, Any]]:
        now = time.monotonic()
        if now < cls._cooldown_until:
            return [], {
                "semantic_status": "cooldown",
                "semantic_elapsed_ms": 0,
                "semantic_query_count": 0,
            }

        started = time.perf_counter()
        output: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)
        thread = threading.Thread(
            target=_run_semantic_task,
            args=(task, output),
            name="semantic-retrieval",
            daemon=True,
        )
        thread.start()
        try:
            status, payload = output.get(timeout=max(timeout_ms, 1) / 1000)
        except queue.Empty:
            cls._cooldown_until = time.monotonic() + max(cooldown_seconds, 0)
            return [], {
                "semantic_status": "timeout",
                "semantic_elapsed_ms": int((time.perf_counter() - started) * 1000),
                "semantic_query_count": 1,
            }
        if status == "error":
            return [], {
                "semantic_status": "error",
                "semantic_elapsed_ms": int((time.perf_counter() - started) * 1000),
                "semantic_query_count": 1,
                "semantic_error": str(payload),
            }

        return list(payload or []), {
            "semantic_status": "ok",
            "semantic_elapsed_ms": int((time.perf_counter() - started) * 1000),
            "semantic_query_count": 1,
        }


def _run_semantic_task(task: Callable[[], list[RetrievedPoi]], output: queue.Queue[tuple[str, Any]]) -> None:
    previous_levels: list[tuple[logging.Logger, int]] = []
    for logger_name in _SEMANTIC_LOGGER_NAMES:
        logger = logging.getLogger(logger_name)
        previous_levels.append((logger, logger.level))
        logger.setLevel(max(logger.level, logging.ERROR))
    try:
        output.put(("ok", task()), block=False)
    except Exception as exc:  # pragma: no cover - exercised through guard error path
        try:
            output.put(("error", exc), block=False)
        except queue.Full:
            pass
    finally:
        for logger, level in previous_levels:
            logger.setLevel(level)


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

    DINING_CATEGORIES = {"restaurant", "cafe"}
    EXPERIENCE_CATEGORIES = {"culture", "scenic", "entertainment", "nightlife", "outdoor"}
    SHOPPING_CATEGORIES = {"shopping"}

    def __init__(
        self,
        repo: PoiRepository | None = None,
        retrieval_service: PoiRetrievalService | None = None,
        semantic_retrieval: RetrievalService | None = None,
    ) -> None:
        self.agent_skill = get_agent_skill_registry().get_skill("recommend")
        self.repo = repo or get_poi_repository()
        self.vector_repo = VectorRepository()
        self.poi_scorer = PoiScoringService()
        self.ugc_repo = self.poi_scorer.ugc_repo
        self.retrieval_service = retrieval_service or PoiRetrievalService(repo=self.repo)
        self.semantic_retrieval = semantic_retrieval or RetrievalService(repo=self.repo)
        self.last_retrieval_stats: dict[str, Any] = {}

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
        retrieval = self.retrieval_service.retrieve_with_stats(request, limit=300)
        structured_candidates = self._prepare_structured_candidates(retrieval.poi_ids, city, request)
        budget_first = self._is_budget_first_request(request, free_text, budget)
        structured_sufficient = self._structured_pool_sufficient(structured_candidates)
        semantic_results: list[RetrievedPoi] = []
        semantic_stats: dict[str, Any] = {
            "semantic_status": "skipped_budget_first",
            "semantic_elapsed_ms": 0,
            "semantic_query_count": 0,
        }
        if not (budget_first and structured_sufficient):
            semantic_results, semantic_stats = self._semantic_candidates_guarded(
                request,
                city,
                persona_tags,
                free_text,
                budget,
                budget_first=budget_first,
            )
        retrieved_by_id = {item.poi_id: item for item in semantic_results}
        semantic_candidates = self.repo.get_many([item.poi_id for item in semantic_results])
        candidates = self._merge_candidate_pois(
            [structured_candidates, semantic_candidates]
            if budget_first
            else [semantic_candidates, structured_candidates]
        )
        self.last_retrieval_stats = {
            **retrieval.stats,
            "retrieval_mode": "budget_first" if budget_first else "semantic_first",
            "structured_candidates": len(structured_candidates),
            "semantic_candidates": len(semantic_results),
            **semantic_stats,
            "rerank_candidates": len(candidates),
        }
        if not candidates:
            candidates = self.repo.list_by_city(city)
            if not candidates and city != "hefei":
                candidates = self.repo.list_by_city("hefei")
            self.last_retrieval_stats = {
                **self.last_retrieval_stats,
                "total_candidates": len(candidates),
                "rerank_candidates": len(candidates),
            }
        else:
            candidates = self._supplement_category_coverage(candidates, city)
            self.last_retrieval_stats["rerank_candidates"] = len(candidates)
        if request.user_facts and request.user_facts.rejected_poi_ids:
            rejected = set(request.user_facts.rejected_poi_ids)
            filtered = [poi for poi in candidates if poi.id not in rejected]
            if len(filtered) >= 3:
                candidates = filtered
        candidates = self._filter_by_radius(candidates, request)
        ugc_by_poi = self._ugc_hits_by_poi(request.ugc_hits)
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
                        context=scoring_context,
                        ugc_by_poi=ugc_by_poi,
                    ),
                    poi,
                )
                for poi in candidates
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        selected = self._select_balanced_pool(scored, request=request, limit=24)
        self.last_retrieval_stats["pool_selected"] = len(selected)
        grouped: dict[str, list[PoiInPool]] = {}
        origin = origin_from_request(request)
        for score, poi in selected:
            retrieved_item = retrieved_by_id.get(poi.id)
            evidence = retrieved_item.evidence_snippets if retrieved_item else []
            breakdown = self.poi_scorer.score_poi(
                poi,
                context=scoring_context,
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
                    latitude=poi.latitude,
                    longitude=poi.longitude,
                    rating=poi.rating,
                    price_per_person=poi.price_per_person,
                    cover_image=poi.cover_image,
                    distance_meters=distance_from_origin(poi, origin),
                    why_recommend=self._why_recommend(
                        poi,
                        poi.tags,
                        free_text,
                        breakdown.history_preference,
                        retrieved_item,
                        weather_condition=request.weather_condition,
                    ),
                    highlight_quote=(
                        evidence[0].text
                        if evidence
                        else self._highlight_quote(poi, free_text, request.ugc_hits)
                    ),
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
                data_warning=self._data_warning(),
            ),
        )
        POOL_REGISTRY[response.pool_id] = response
        return response

    def _prepare_structured_candidates(
        self,
        poi_ids: list[str],
        city: str,
        request: PoolRequest,
    ) -> list[PoiDetail]:
        candidates = self.repo.get_many(list(dict.fromkeys(poi_ids)))
        if not candidates:
            candidates = self.repo.list_by_city(city)
            if not candidates and city != "hefei":
                candidates = self.repo.list_by_city("hefei")
        else:
            candidates = self._supplement_category_coverage(candidates, city)
        return self._filter_user_and_radius(candidates, request)

    def _filter_user_and_radius(self, candidates: list[PoiDetail], request: PoolRequest) -> list[PoiDetail]:
        if request.user_facts and request.user_facts.rejected_poi_ids:
            rejected = set(request.user_facts.rejected_poi_ids)
            filtered = [poi for poi in candidates if poi.id not in rejected]
            if len(filtered) >= 3:
                candidates = filtered
        return self._filter_by_radius(candidates, request)

    def _merge_candidate_pois(self, groups: list[list[PoiDetail]]) -> list[PoiDetail]:
        merged: list[PoiDetail] = []
        seen: set[str] = set()
        for group in groups:
            for poi in group:
                poi_id = getattr(poi, "id", None)
                if not poi_id or poi_id in seen:
                    continue
                merged.append(poi)
                seen.add(poi_id)
        return merged

    def _is_budget_first_request(
        self,
        request: PoolRequest,
        free_text: str | None,
        budget: int | None,
    ) -> bool:
        settings = get_settings()
        threshold = int(getattr(settings, "budget_first_threshold", 100) or 100)
        if budget is not None and budget <= threshold:
            return True
        text = (free_text or request.free_text or "").lower()
        return any(
            token in text
            for token in [
                "budget friendly",
                "budget-friendly",
                "budget tight",
                "low budget",
                "no expensive",
                "not expensive",
                "cheap",
                "under ",
                "within budget",
                "\u9884\u7b97\u7d27",
                "\u9884\u7b97\u6709\u9650",
                "\u63a7\u5236\u9884\u7b97",
                "\u4e0d\u8d85\u9884\u7b97",
                "\u4e0d\u8d85\u8fc7",
                "\u4ee5\u5185",
            ]
        )

    def _structured_pool_sufficient(self, candidates: list[PoiDetail]) -> bool:
        if len(candidates) < 24:
            return False
        categories = {poi.category for poi in candidates}
        return "restaurant" in categories and bool(categories - {"restaurant"})

    def _semantic_candidates_guarded(
        self,
        request: PoolRequest,
        city: str,
        persona_tags: list[str],
        free_text: str | None,
        budget: int | None,
        *,
        budget_first: bool,
    ) -> tuple[list[RetrievedPoi], dict[str, Any]]:
        settings = get_settings()
        if not getattr(settings, "rag_enabled", True):
            return [], {
                "semantic_status": "disabled",
                "semantic_elapsed_ms": 0,
                "semantic_query_count": 0,
            }
        vector_index = getattr(self.semantic_retrieval, "vector_index", _MISSING)
        if vector_index is None:
            return [], {
                "semantic_status": "disabled",
                "semantic_elapsed_ms": 0,
                "semantic_query_count": 0,
            }
        timeout_ms = (
            int(getattr(settings, "budget_first_semantic_timeout_ms", 600) or 600)
            if budget_first
            else int(getattr(settings, "semantic_retrieval_timeout_ms", 1200) or 1200)
        )
        cooldown_seconds = int(getattr(settings, "semantic_timeout_cooldown_seconds", 60) or 60)
        return SemanticRetrievalGuard.run(
            lambda: self._semantic_candidates(request, city, persona_tags, free_text, budget),
            timeout_ms=timeout_ms,
            cooldown_seconds=cooldown_seconds,
        )

    def _score_poi(
        self,
        poi: PoiDetail,
        persona_tags: list[str],
        free_text: str | None,
        budget_per_person: int | None,
        request: PoolRequest | None = None,
        context=None,
        ugc_by_poi: dict[str, list[dict[str, Any]]] | None = None,
    ) -> float:
        rating_score = poi.rating / 5 * 0.22
        semantic_score = self.vector_repo.score(poi, persona_tags, free_text) * 0.24
        popularity_score = min(poi.review_count / 1200, 1) * 0.08
        queue_bonus = max(0, (60 - poi.queue_estimate["weekend_peak"]) / 60) * 0.08
        profile_score = self._cheap_profile_score(poi, request, free_text) * 0.24
        history_score = self._cheap_history_score(poi, request) * 0.20
        ugc_bonus = 0.10 if ugc_by_poi and poi.id in ugc_by_poi else 0.0
        explicit_category_bonus = self._explicit_category_bonus(poi, free_text)
        distance_penalty = self._distance_penalty_score(poi, context)
        weather_adjustment = self._weather_adjustment_score(poi, context)
        budget_penalty = 0.0
        if budget_per_person and poi.price_per_person and poi.price_per_person > budget_per_person:
            budget_penalty = min((poi.price_per_person - budget_per_person) / max(budget_per_person, 1), 2) * 0.18
        return float(max(
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
                + explicit_category_bonus
                + weather_adjustment
                - budget_penalty
                - distance_penalty,
            ),
        ))

    def _why_recommend(
        self,
        poi: PoiDetail,
        tags: list[str],
        free_text: str | None,
        history_preference: float,
        retrieved_item: RetrievedPoi | None = None,
        weather_condition: str = "normal",
    ) -> str:
        name = poi.name
        if weather_condition == "rainy" and poi.category in {"culture", "shopping", "cafe", "entertainment", "restaurant"}:
            return f"{name}更适合雨天安排，室内停留稳定，也方便和周边点位串联。"
        if weather_condition == "hot" and poi.category in {"cafe", "shopping", "culture", "entertainment", "restaurant"}:
            return f"{name}适合炎热天气下作为室内或短停留节点，能降低暴晒和长距离移动成本。"
        if weather_condition == "cold" and poi.category in {"restaurant", "cafe", "shopping", "culture", "entertainment"}:
            return f"{name}适合偏冷天气下安排，停留环境更稳定。"
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

    def _weather_adjustment_score(self, poi: PoiDetail, context) -> float:
        weather = getattr(context, "weather_condition", "normal") if context is not None else "normal"
        distance = distance_from_origin(poi, origin_from_context(context)) if context is not None else None
        if weather == "rainy":
            if poi.category in {"culture", "shopping", "cafe", "entertainment", "restaurant"}:
                return 0.12
            if poi.category in {"outdoor", "scenic"}:
                return -0.18
        if weather == "hot":
            score = 0.10 if poi.category in {"cafe", "shopping", "culture", "entertainment", "restaurant"} else 0.0
            if poi.category in {"outdoor", "scenic"}:
                score -= 0.12
            if distance is not None and distance > 4500:
                score -= 0.08
            return score
        if weather == "cold":
            if poi.category in {"restaurant", "cafe", "shopping", "culture", "entertainment"}:
                return 0.08
            if poi.category in {"outdoor", "scenic"}:
                return -0.08
        return 0.0

    def _explicit_category_bonus(self, poi: PoiDetail, free_text: str | None) -> float:
        text = (free_text or "").lower()
        if not text:
            return 0.0
        if any(keyword in text for keyword in ["culture", "museum", "gallery", "exhibition", "art"]):
            if poi.category == "culture":
                return 0.18
            if poi.category == "scenic":
                return 0.04
        if any(keyword in text for keyword in ["cafe", "cafes", "coffee"]) and poi.category == "cafe":
            return 0.16
        if any(keyword in text for keyword in ["shopping", "mall", "shop"]) and poi.category == "shopping":
            return 0.04
        if any(keyword in text for keyword in ["food", "restaurant", "local food", "lunch", "dinner"]):
            return 0.06 if poi.category == "restaurant" else 0.0
        return 0.0

    def _semantic_candidates(
        self,
        request: PoolRequest,
        city: str,
        persona_tags: list[str],
        free_text: str | None,
        budget: int | None,
    ) -> list[RetrievedPoi]:
        terms = list(persona_tags)
        if request.preference_snapshot:
            terms.extend(list(request.preference_snapshot.category_weights)[:6])
            terms.extend(list(request.preference_snapshot.tag_weights)[:8])
            terms.extend(list(request.preference_snapshot.keyword_weights)[:8])
        profile = request.need_profile
        if profile:
            terms.extend(profile.activity_preferences)
            terms.extend(profile.food_preferences)
            terms.extend(profile.route_style)
        origin = origin_from_request(request)
        results = self.semantic_retrieval.retrieve(
            RetrievalQuery(
                city=city,
                text=free_text,
                top_k=120,
                budget_per_person=budget,
                avoid_queue="少排队" in (free_text or ""),
                preference_terms=list(dict.fromkeys(terms)),
                origin_latitude=origin[0] if origin else None,
                origin_longitude=origin[1] if origin else None,
                radius_meters=radius_from_request(request),
                source_types=["poi_profile", "ugc_review"],
            )
        )
        return results[:80]

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

    def _highlight_quote(self, poi, free_text: str | None, ugc_hits: list[dict[str, Any]] | None = None) -> str | None:
        for hit in ugc_hits or []:
            if str(hit.get("poi_id")) == poi.id and hit.get("snippet"):
                return str(hit["snippet"])
        if ugc_hits:
            return poi.highlight_quotes[0].quote if poi.highlight_quotes else None
        indexed_quote = self.retrieval_service.evidence_for_poi(poi.id, free_text)
        if indexed_quote:
            return indexed_quote
        hits = self.ugc_repo.evidence_for_poi(poi.id, free_text or "", top_k=1)
        if hits:
            return hits[0].snippet
        return poi.highlight_quotes[0].quote if poi.highlight_quotes else None

    def _ugc_hits_by_poi(self, ugc_hits: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for hit in ugc_hits:
            poi_id = str(hit.get("poi_id") or "")
            if poi_id:
                grouped.setdefault(poi_id, []).append(hit)
        return grouped

    def _cheap_profile_score(self, poi, request: PoolRequest | None, free_text: str | None) -> float:
        score = 0.45
        profile = request.need_profile if request else None
        text = free_text or ""
        lowered = text.lower()
        if profile and profile.party_type and profile.party_type in poi.suitable_for:
            score += 0.12
        if any(keyword in lowered for keyword in ["food", "restaurant", "local food", "lunch", "dinner"]):
            score += 0.18 if poi.category == "restaurant" else 0.0
        if any(keyword in lowered for keyword in ["cafe", "cafes", "coffee"]):
            score += 0.28 if poi.category == "cafe" else 0.0
        if any(keyword in lowered for keyword in ["culture", "museum", "gallery", "exhibition", "art"]):
            score += 0.44 if poi.category == "culture" else 0.04 if poi.category == "scenic" else 0.0
        if any(keyword in lowered for keyword in ["shopping", "mall", "shop"]):
            score += 0.2 if poi.category == "shopping" else 0.0
        if any(keyword in lowered for keyword in ["rainy", "indoor"]) and poi.category in {
            "culture",
            "cafe",
            "shopping",
            "entertainment",
        }:
            score += 0.08
        if any(keyword in text for keyword in ["吃", "餐", "美食", "本地菜", "火锅"]):
            score += 0.18 if poi.category == "restaurant" else 0.0
        if "咖啡" in text and poi.category == "cafe":
            score += 0.14
        if any(keyword in text for keyword in ["拍照", "打卡"]) and (
            "photogenic" in poi.tags or "拍照" in poi.tags or "打卡" in poi.tags
        ):
            score += 0.12
        return min(score, 1.0)

    def _distance_penalty_score(self, poi, context) -> float:
        distance = distance_from_origin(poi, origin_from_context(context))
        if distance is None or distance <= 1500:
            return 0.0
        return min((distance - 1500) / 1000 * 0.02, 0.18)

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
        self._append_best_category(defaults, all_pois, self.SHOPPING_CATEGORIES, request)
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
                    latitude=poi.latitude,
                    longitude=poi.longitude,
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

    def _data_warning(self) -> str | None:
        if get_settings().rag_enabled and getattr(self.semantic_retrieval, "vector_index", None) is None:
            return "FAISS index missing; using SQLite/seed fallback."
        return None

    def _filter_by_radius(self, candidates: list[PoiDetail], request: PoolRequest) -> list[PoiDetail]:
        radius_meters = radius_from_request(request)
        if radius_meters is None:
            return candidates
        origin = origin_from_request(request)
        if origin is None:
            return candidates
        return [poi for poi in candidates if within_radius(poi, origin, radius_meters)]

    def _supplement_category_coverage(self, candidates: list[PoiDetail], city: str) -> list[PoiDetail]:
        present = {getattr(poi, "category", None) for poi in candidates}
        missing_groups = []
        if not present & self.DINING_CATEGORIES:
            missing_groups.append(self.DINING_CATEGORIES)
        if not present & self.EXPERIENCE_CATEGORIES:
            missing_groups.append(self.EXPERIENCE_CATEGORIES)
        if not present & self.SHOPPING_CATEGORIES:
            missing_groups.append(self.SHOPPING_CATEGORIES)
        if not missing_groups:
            return candidates

        extended = list(candidates)
        existing_ids = {getattr(poi, "id", None) for poi in extended}
        city_candidates = self.repo.list_by_city(city)
        if not city_candidates and city != "hefei":
            city_candidates = self.repo.list_by_city("hefei")
        for group in missing_groups:
            added = 0
            for poi in city_candidates:
                poi_id = getattr(poi, "id", None)
                if poi_id in existing_ids or getattr(poi, "category", None) not in group:
                    continue
                extended.append(poi)
                existing_ids.add(poi_id)
                added += 1
                if added >= 12:
                    break
        return extended

    def _select_balanced_pool(
        self,
        scored: list[tuple[float, PoiDetail]],
        *,
        request: PoolRequest,
        limit: int,
    ) -> list[tuple[float, PoiDetail]]:
        if limit <= 0:
            return []
        dining_target, experience_target, shopping_target = self._pool_targets(limit, request)
        selected: list[tuple[float, PoiDetail]] = []
        used_ids: set[str] = set()

        self._take_scored(scored, selected, used_ids, categories=self.DINING_CATEGORIES, count=dining_target)
        self._take_scored(scored, selected, used_ids, categories=self.EXPERIENCE_CATEGORIES, count=experience_target)
        self._take_scored(scored, selected, used_ids, categories=self.SHOPPING_CATEGORIES, count=shopping_target)
        if len(selected) < limit:
            self._take_scored(scored, selected, used_ids, categories=None, count=limit - len(selected))
        return selected[:limit]

    def _pool_targets(self, limit: int, request: PoolRequest) -> tuple[int, int, int]:
        dining = max(1, round(limit * 0.58))
        experience = max(1, round(limit * 0.29))
        shopping = max(0, limit - dining - experience)
        if limit >= 6:
            shopping = max(1, shopping)

        text = (request.free_text or "").lower()
        avoids_shopping = self._request_avoids_shopping(text)
        if avoids_shopping:
            shopping = 0
        if not avoids_shopping and any(
            token in text for token in ["shopping", "mall", "shop", "商场", "购物", "逛街", "步行街", "商业街"]
        ):
            shopping = max(shopping, min(4, round(limit * 0.2)))
        if any(
            token in text
            for token in [
                "scenic",
                "park",
                "walk",
                "culture",
                "museum",
                "gallery",
                "exhibition",
                "art",
                "景点",
                "公园",
                "文化",
                "展览",
                "散步",
                "拍照",
            ]
        ):
            experience = max(experience, round(limit * 0.33))

        while dining + experience + shopping > limit:
            dining -= 1
        return dining, experience, shopping

    def _take_scored(
        self,
        scored: list[tuple[float, PoiDetail]],
        selected: list[tuple[float, PoiDetail]],
        used_ids: set[str],
        *,
        categories: set[str] | None,
        count: int,
    ) -> None:
        if count <= 0:
            return
        added = 0
        for score, poi in scored:
            poi_id = getattr(poi, "id", None)
            if not poi_id or poi_id in used_ids:
                continue
            if categories is not None and getattr(poi, "category", None) not in categories:
                continue
            selected.append((score, poi))
            used_ids.add(poi_id)
            added += 1
            if added >= count:
                return

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
        if poi.category == "shopping" and self._request_avoids_shopping(request.free_text or ""):
            return False
        if request.budget_per_person and poi.price_per_person:
            if poi.price_per_person > request.budget_per_person:
                return False
        if "少排队" in (request.free_text or "") and (poi.estimated_queue_min or 0) > 45:
            return False
        return True

    def _request_avoids_shopping(self, text: str) -> bool:
        return any(keyword in text for keyword in ["不要商场", "不去商场", "别去商场", "少逛街"])

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

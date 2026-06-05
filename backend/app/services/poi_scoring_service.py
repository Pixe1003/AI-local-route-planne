from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import PlanContext, ScoreBreakdown, StructuredIntent
from app.schemas.preferences import PreferenceSnapshot
from app.schemas.user_memory import UserFacts
from app.config import get_settings
from app.ml.features import build_features, ugc_sim_from_match
from app.ml.ranker import get_ranker
from app.repositories.ugc_vector_repo import UgcVectorRepo, get_ugc_vector_repo
from app.services.location_context import distance_from_origin, origin_from_context


class PoiScoringService:
    def __init__(self, ugc_repo: UgcVectorRepo | None = None) -> None:
        self.ugc_repo = ugc_repo or get_ugc_vector_repo()

    def score_poi(
        self,
        poi,
        *,
        intent: StructuredIntent | None = None,
        context: PlanContext | None = None,
        profile: UserNeedProfile | None = None,
        preference_snapshot: PreferenceSnapshot | None = None,
        free_text: str | None = None,
        user_facts: UserFacts | None = None,
    ) -> ScoreBreakdown:
        text = " ".join(
            [
                free_text or "",
                profile.raw_query if profile and profile.raw_query else "",
                " ".join(profile.activity_preferences) if profile else "",
                " ".join(profile.food_preferences) if profile else "",
                " ".join(profile.route_style) if profile else "",
            ]
        )
        user_interest = self._user_interest_score(poi, text, profile, context)
        poi_quality = min((poi.rating or 0) / 5 * 25 + min(poi.review_count / 1200, 1) * 8, 30)
        context_fit = self._context_fit_score(poi, context, profile)
        ugc_match = self._ugc_match_score(poi, text)
        service_closure = 8.0 if poi.price_per_person is not None else 4.0
        history_preference = self._history_preference_score(poi, preference_snapshot)
        fact_alignment = self._fact_alignment_score(poi, user_facts)
        queue_penalty = self._queue_penalty(poi, intent, text)
        price_penalty = self._price_penalty(poi, intent, profile)
        distance_penalty = self._distance_penalty(poi, context)
        risk_penalty = -4.0 if poi.queue_estimate["weekend_peak"] > 45 else 0.0
        total = (
            user_interest
            + poi_quality
            + context_fit
            + ugc_match
            + service_closure
            + history_preference
            + fact_alignment
            + queue_penalty
            + price_penalty
            + distance_penalty
            + risk_penalty
        )
        breakdown = ScoreBreakdown(
            user_interest=round(user_interest, 2),
            poi_quality=round(poi_quality, 2),
            context_fit=round(context_fit, 2),
            ugc_match=round(ugc_match, 2),
            service_closure=round(service_closure, 2),
            history_preference=round(history_preference, 2),
            fact_alignment=round(fact_alignment, 2),
            queue_penalty=round(queue_penalty, 2),
            price_penalty=round(price_penalty, 2),
            distance_penalty=round(distance_penalty, 2),
            risk_penalty=round(risk_penalty, 2),
            total=round(total, 2),
        )
        model_score = self._ranker_score(poi, breakdown, context, ugc_match)
        if model_score is not None:
            breakdown.total = round(model_score, 2)
        return breakdown

    def _ranker_score(
        self,
        poi,
        breakdown: ScoreBreakdown,
        context: PlanContext | None,
        ugc_match: float,
    ) -> float | None:
        settings = get_settings()
        if not settings.ranker_enabled:
            return None
        distance = self._raw_distance_m(poi, context)
        ugc_sim = ugc_sim_from_match(ugc_match)
        features = build_features(poi, breakdown, distance_m=distance or 0, ugc_sim=ugc_sim)
        return get_ranker(settings.ranker_model_path).predict(features)

    def _user_interest_score(
        self,
        poi,
        text: str,
        profile: UserNeedProfile | None,
        context: PlanContext | None,
    ) -> float:
        score = 8.0
        tags = set(poi.tags + poi.suitable_for + poi.atmosphere)
        if profile and profile.party_type and profile.party_type in tags:
            score += 7
        if any(keyword in text for keyword in ["拍照", "打卡", "photogenic"]):
            score += 4 if "photogenic" in tags or "拍照" in tags else 0
        if any(keyword in text for keyword in ["吃", "饭", "美食", "本地菜", "本地口味"]):
            score += 7 if poi.category == "restaurant" else 0
        if "咖啡" in text and poi.category == "cafe":
            score += 5
        weather = getattr(context, "weather_condition", "normal") if context is not None else "normal"
        if "雨天" in text or "下雨" in text or weather == "rainy":
            score += 4 if poi.category in {"culture", "shopping", "cafe", "restaurant"} else -4
        if weather == "hot":
            score += 3 if poi.category in {"cafe", "shopping", "culture", "restaurant"} else 0
            score -= 3 if poi.category in {"outdoor", "scenic"} else 0
        if weather == "cold":
            score += 2 if poi.category in {"restaurant", "cafe", "shopping", "culture"} else 0
            score -= 2 if poi.category in {"outdoor", "scenic"} else 0
        return max(0.0, min(score, 25.0))

    def _context_fit_score(
        self, poi, context: PlanContext | None, profile: UserNeedProfile | None
    ) -> float:
        score = 10.0
        route_styles = set(profile.route_style if profile else [])
        if "少排队" in route_styles and poi.queue_estimate["weekend_peak"] <= 25:
            score += 5
        if profile and profile.party_type == "senior" and poi.category in {"outdoor", "entertainment"}:
            score -= 4
        return max(0.0, min(score, 18.0))

    def _ugc_match_score(self, poi, text: str) -> float:
        score = 6.0
        hits = self.ugc_repo.evidence_for_poi(poi.id, text, top_k=3)
        if hits:
            best_hit = max(hits, key=lambda hit: hit.score)
            score += min(best_hit.score, 10.0)

        keyword_text = " ".join(str(item["keyword"]) for item in poi.high_freq_keywords)
        combined = f"{keyword_text} {' '.join(poi.tags)}"
        if "本地" in text and "本地口味" in combined:
            score += 5
        if "排队" in text and "低排队" in combined:
            score += 5
        if "拍照" in text and ("拍照" in combined or "打卡" in combined):
            score += 4
        return min(score, 18.0)

    def _history_preference_score(self, poi, snapshot: PreferenceSnapshot | None) -> float:
        if snapshot is None:
            return 0.0
        if poi.id in snapshot.disliked_poi_ids:
            return -16.0
        score = 0.0
        if poi.id in snapshot.liked_poi_ids:
            score += 14.0
        score += snapshot.category_weights.get(poi.category, 0.0) * 5.0
        for tag in poi.tags + poi.suitable_for + poi.atmosphere:
            score += snapshot.tag_weights.get(tag, 0.0) * 1.2
        for item in poi.high_freq_keywords:
            score += snapshot.keyword_weights.get(str(item.get("keyword", "")), 0.0) * 1.5
        return max(-16.0, min(score, 22.0))

    def _fact_alignment_score(self, poi, facts: UserFacts | None) -> float:
        if facts is None or facts.session_count <= 0:
            return 0.0
        if poi.id in facts.rejected_poi_ids:
            return -16.0
        score = 0.0
        if poi.category in facts.favorite_categories:
            score += 6.0
        if poi.category in facts.avoid_categories:
            score -= 10.0
        if facts.favorite_districts:
            poi_district = getattr(poi, "district", None)
            address = getattr(poi, "address", "") or ""
            if poi_district and poi_district in facts.favorite_districts:
                score += 2.0
            elif any(district in address for district in facts.favorite_districts):
                score += 2.0
        if facts.typical_budget_range and poi.price_per_person:
            _, high = facts.typical_budget_range
            if poi.price_per_person > high:
                score -= 4.0
        return max(-16.0, min(score, 10.0))

    def _queue_penalty(self, poi, intent: StructuredIntent | None, text: str) -> float:
        penalty = -min(float(poi.queue_estimate["weekend_peak"]) / 60 * 12, 12.0)
        if intent and intent.soft_preferences.avoid_queue:
            penalty *= 1.4
        if "少排队" in text or "不排队" in text:
            penalty *= 1.2
        return float(penalty)

    def _price_penalty(
        self, poi, intent: StructuredIntent | None, profile: UserNeedProfile | None
    ) -> float:
        budget = profile.budget.budget_per_person if profile else None
        if budget is None and intent and intent.hard_constraints.budget_total:
            budget = intent.hard_constraints.budget_total
        if budget and poi.price_per_person and poi.price_per_person > budget:
            return -14.0
        return 0.0

    def _distance_penalty(self, poi, context: PlanContext | None) -> float:
        distance = self._raw_distance_m(poi, context)
        if distance is None or distance <= 1500:
            return 0.0
        return -min((distance - 1500) / 1000 * 1.8, 18.0)

    def _raw_distance_m(self, poi, context: PlanContext | None) -> float | None:
        origin = origin_from_context(context)
        if origin is None:
            return None
        return distance_from_origin(poi, origin)

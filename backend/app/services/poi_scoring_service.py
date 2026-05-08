from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import PlanContext, ScoreBreakdown, StructuredIntent
from app.schemas.preferences import PreferenceSnapshot


class PoiScoringService:
    def score_poi(
        self,
        poi,
        *,
        intent: StructuredIntent | None = None,
        context: PlanContext | None = None,
        profile: UserNeedProfile | None = None,
        preference_snapshot: PreferenceSnapshot | None = None,
        free_text: str | None = None,
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
        user_interest = self._user_interest_score(poi, text, profile)
        poi_quality = min((poi.rating or 0) / 5 * 25 + min(poi.review_count / 1200, 1) * 8, 30)
        context_fit = self._context_fit_score(poi, context, profile)
        ugc_match = self._ugc_match_score(poi, text)
        service_closure = 8.0 if poi.price_per_person is not None else 4.0
        history_preference = self._history_preference_score(poi, preference_snapshot)
        queue_penalty = self._queue_penalty(poi, intent, text)
        price_penalty = self._price_penalty(poi, intent, profile)
        distance_penalty = 0.0
        risk_penalty = -4.0 if poi.queue_estimate["weekend_peak"] > 45 else 0.0
        total = (
            user_interest
            + poi_quality
            + context_fit
            + ugc_match
            + service_closure
            + history_preference
            + queue_penalty
            + price_penalty
            + distance_penalty
            + risk_penalty
        )
        return ScoreBreakdown(
            user_interest=round(user_interest, 2),
            poi_quality=round(poi_quality, 2),
            context_fit=round(context_fit, 2),
            ugc_match=round(ugc_match, 2),
            service_closure=round(service_closure, 2),
            history_preference=round(history_preference, 2),
            queue_penalty=round(queue_penalty, 2),
            price_penalty=round(price_penalty, 2),
            distance_penalty=round(distance_penalty, 2),
            risk_penalty=round(risk_penalty, 2),
            total=round(total, 2),
        )

    def _user_interest_score(self, poi, text: str, profile: UserNeedProfile | None) -> float:
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
        if "雨天" in text or "下雨" in text:
            score += 4 if poi.category in {"culture", "shopping", "cafe", "restaurant"} else -4
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

    def _queue_penalty(self, poi, intent: StructuredIntent | None, text: str) -> float:
        penalty = -min(poi.queue_estimate["weekend_peak"] / 60 * 12, 12)
        if intent and intent.soft_preferences.avoid_queue:
            penalty *= 1.4
        if "少排队" in text or "不排队" in text:
            penalty *= 1.2
        return penalty

    def _price_penalty(
        self, poi, intent: StructuredIntent | None, profile: UserNeedProfile | None
    ) -> float:
        budget = profile.budget.budget_per_person if profile else None
        if budget is None and intent and intent.hard_constraints.budget_total:
            budget = intent.hard_constraints.budget_total
        if budget and poi.price_per_person and poi.price_per_person > budget:
            return -14.0
        return 0.0

from typing import Any

from app.schemas.plan import ScoreBreakdown


FEATURE_ORDER = [
    "user_interest",
    "poi_quality",
    "context_fit",
    "ugc_match",
    "service_closure",
    "history_preference",
    "fact_alignment",
    "queue_penalty",
    "price_penalty",
    "distance_penalty",
    "risk_penalty",
    "queue_min",
    "price",
    "distance_m",
    "ugc_sim",
    "popularity",
]


def ugc_sim_from_match(ugc_match: float) -> float:
    """Map the existing rule score onto the bounded online ranker feature."""
    return max(0.0, min((float(ugc_match) - 6.0) / 10.0, 1.0))


def build_features(
    poi: Any,
    breakdown: ScoreBreakdown,
    *,
    distance_m: float = 0.0,
    ugc_sim: float = 0.0,
) -> list[float]:
    queue = getattr(poi, "queue_estimate", {}) or {}
    return [
        breakdown.user_interest,
        breakdown.poi_quality,
        breakdown.context_fit,
        breakdown.ugc_match,
        breakdown.service_closure,
        breakdown.history_preference,
        breakdown.fact_alignment,
        breakdown.queue_penalty,
        breakdown.price_penalty,
        breakdown.distance_penalty,
        breakdown.risk_penalty,
        float(queue.get("weekend_peak", 0)),
        float(getattr(poi, "price_per_person", None) or 0),
        float(distance_m or 0),
        float(ugc_sim or 0),
        float(getattr(poi, "review_count", 0) or 0),
    ]

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class EvalResult:
    scenario_id: str
    feasible: bool
    constraints_satisfied: bool
    explanation_faithfulness: float
    tool_count: int = 0
    total_tokens: int = 0
    total_latency_ms: int = 0
    route_quality_gap: float | None = None
    ndcg_at_5: float | None = None
    route_variant_count: int = 0
    on_time_prob: float | None = None
    variant_jaccard_overlap: float | None = None
    category_entropy: float | None = None
    business_area_spread: float | None = None
    soft_constraint_tradeoff_score: float | None = None
    scenario_expectation_passed: bool = True


def explanation_faithfulness(story: Any, poi_by_id: dict[str, Any]) -> float:
    ok = 0
    total = 0
    for stop in getattr(story, "stops", []) or []:
        total += 1
        poi = poi_by_id.get(stop.poi_id)
        if poi is not None and _why_matches_poi(stop.why, poi):
            ok += 1
    return round(ok / max(total, 1), 3)


def aggregate(results: list[EvalResult]) -> dict[str, float]:
    total = max(len(results), 1)
    gaps = [item.route_quality_gap for item in results if item.route_quality_gap is not None]
    ndcgs = [item.ndcg_at_5 for item in results if item.ndcg_at_5 is not None]
    on_time_probs = [item.on_time_prob for item in results if item.on_time_prob is not None]
    overlaps = [item.variant_jaccard_overlap for item in results if item.variant_jaccard_overlap is not None]
    entropies = [item.category_entropy for item in results if item.category_entropy is not None]
    area_spreads = [item.business_area_spread for item in results if item.business_area_spread is not None]
    tradeoff_scores = [
        item.soft_constraint_tradeoff_score
        for item in results
        if item.soft_constraint_tradeoff_score is not None
    ]
    return {
        "scenario_count": float(len(results)),
        "feasible_rate": round(sum(item.feasible for item in results) / total, 3),
        "constraint_satisfaction_rate": round(
            sum(item.constraints_satisfied for item in results) / total, 3
        ),
        "explanation_faithfulness": round(
            sum(item.explanation_faithfulness for item in results) / total, 3
        ),
        "avg_tool_count": round(sum(item.tool_count for item in results) / total, 2),
        "avg_latency_ms": round(sum(item.total_latency_ms for item in results) / total, 2),
        "total_tokens": float(sum(item.total_tokens for item in results)),
        "avg_route_quality_gap": round(sum(gaps) / max(len(gaps), 1), 3),
        "avg_ndcg_at_5": round(sum(ndcgs) / max(len(ndcgs), 1), 3),
        "avg_route_variant_count": round(sum(item.route_variant_count for item in results) / total, 2),
        "avg_on_time_prob": round(sum(on_time_probs) / max(len(on_time_probs), 1), 3),
        "avg_variant_jaccard_overlap": round(sum(overlaps) / max(len(overlaps), 1), 3),
        "avg_category_entropy": round(sum(entropies) / max(len(entropies), 1), 3),
        "avg_business_area_spread": round(sum(area_spreads) / max(len(area_spreads), 1), 3),
        "avg_soft_constraint_tradeoff_score": round(
            sum(tradeoff_scores) / max(len(tradeoff_scores), 1),
            3,
        ),
        "scenario_expectation_pass_rate": round(
            sum(item.scenario_expectation_passed for item in results) / total,
            3,
        ),
    }


def _why_matches_poi(why: str, poi: Any) -> bool:
    text = why.lower()
    category = str(getattr(poi, "category", "") or "").lower()
    if category and category in text:
        return True
    rating = getattr(poi, "rating", None)
    if rating is not None and re.search(rf"\b{float(rating):.1f}\b", text):
        return True
    for item in getattr(poi, "high_freq_keywords", []) or []:
        keyword = str(item.get("keyword", "")).lower()
        if keyword and keyword in text:
            return True
    return False

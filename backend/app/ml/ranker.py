from __future__ import annotations

from functools import lru_cache
from math import log2
from pathlib import Path


class PoiRanker:
    def __init__(self, model_path: str | Path = "data/models/ranker.txt") -> None:
        self.model_path = Path(model_path)
        self.model = None
        if not self.model_path.exists():
            return
        try:
            import lightgbm as lgb
        except Exception:
            return
        self.model = lgb.Booster(model_file=str(self.model_path))

    def predict(self, features: list[float]) -> float | None:
        if self.model is None:
            return None
        score = self.model.predict([features])[0]
        return float(score)


@lru_cache(maxsize=4)
def get_ranker(model_path: str) -> PoiRanker:
    return PoiRanker(model_path)


def ndcg_at_k(relevances: list[float], *, k: int = 5) -> float:
    top = relevances[:k]
    ideal = sorted(relevances, reverse=True)[:k]
    ideal_score = _dcg(ideal)
    if ideal_score <= 0:
        return 0.0
    return round(_dcg(top) / ideal_score, 6)


def should_enable_ranker(
    *,
    model_ndcg: float,
    baseline_ndcg: float,
    min_relative_gain: float = 0.03,
) -> bool:
    if baseline_ndcg <= 0:
        return model_ndcg > 0
    return (model_ndcg - baseline_ndcg) / baseline_ndcg >= min_relative_gain


def _dcg(relevances: list[float]) -> float:
    return sum((2**rel - 1) / log2(index + 2) for index, rel in enumerate(relevances))

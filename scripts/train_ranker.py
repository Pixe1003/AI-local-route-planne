from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.ml.features import build_features, ugc_sim_from_match
from app.ml.ranker import ndcg_at_k, should_enable_ranker
from app.repositories.poi_repo import get_poi_repository
from app.services.poi_scoring_service import PoiScoringService


SYNTH_QUERIES: list[dict[str, Any]] = [
    {
        "id": "food_photo",
        "text": "local food photogenic cafe culture",
        "category_boost": {"restaurant": 2, "cafe": 1, "culture": 1},
        "avoid_queue": False,
        "budget": None,
    },
    {
        "id": "budget_tight",
        "text": "budget friendly local food low cost",
        "category_boost": {"restaurant": 1, "cafe": 1, "culture": 1},
        "avoid_queue": False,
        "budget": 80,
    },
    {
        "id": "low_queue",
        "text": "low queue efficient quiet route",
        "category_boost": {"restaurant": 1, "culture": 1, "scenic": 1},
        "avoid_queue": True,
        "budget": None,
    },
    {
        "id": "rainy_indoor",
        "text": "rainy day indoor culture cafe shopping",
        "category_boost": {"culture": 2, "cafe": 1, "shopping": 1, "restaurant": 1},
        "avoid_queue": False,
        "budget": None,
    },
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the AIroute weak-supervision POI ranker.")
    parser.add_argument("--city", default="hefei")
    parser.add_argument("--model-out", default="data/models/ranker.txt")
    parser.add_argument("--report-out", default="data/eval/ranker_train.json")
    args = parser.parse_args()

    try:
        import lightgbm as lgb
        import numpy as np
    except Exception as exc:
        raise SystemExit("lightgbm and numpy are required. Run backend dependency install first.") from exc

    pois = get_poi_repository().list_by_city(args.city, limit=200)
    rows, labels, groups, baseline_scores = _build_dataset(pois)
    if len(rows) < 10:
        raise SystemExit(f"Need at least 10 POIs to train ranker, got {len(rows)}")

    split_group_count = max(1, int(len(groups) * 0.75))
    train_size = sum(groups[:split_group_count])
    train_rows, valid_rows = rows[:train_size], rows[train_size:]
    train_labels, valid_labels = labels[:train_size], labels[train_size:]
    train_groups, valid_groups = groups[:split_group_count], groups[split_group_count:]
    valid_baseline_scores = baseline_scores[train_size:]
    train_matrix = np.asarray(train_rows, dtype="float32")
    valid_matrix = np.asarray(valid_rows, dtype="float32")
    train_set = lgb.Dataset(train_matrix, label=np.asarray(train_labels, dtype="float32"), group=train_groups)
    model = lgb.train(
        {
            "objective": "lambdarank",
            "metric": "ndcg",
            "verbosity": -1,
            "learning_rate": 0.05,
            "num_leaves": 15,
            "min_data_in_leaf": 2,
        },
        train_set,
        num_boost_round=30,
    )
    predictions = list(model.predict(valid_matrix))
    model_ndcg = _group_ndcg(valid_labels, predictions, valid_groups)
    baseline_ndcg = _group_ndcg(valid_labels, valid_baseline_scores, valid_groups)
    enabled = should_enable_ranker(model_ndcg=model_ndcg, baseline_ndcg=baseline_ndcg)

    model_out = ROOT / args.model_out
    model_out.parent.mkdir(parents=True, exist_ok=True)
    _save_model(model, model_out)
    report = {
        "city": args.city,
        "training_rows": len(train_rows),
        "validation_rows": len(valid_rows),
        "query_groups": len(groups),
        "model_ndcg_at_5": model_ndcg,
        "baseline_ndcg_at_5": baseline_ndcg,
        "ranker_enabled_recommended": enabled,
    }
    report_out = ROOT / args.report_out
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _build_dataset(pois: list[Any]) -> tuple[list[list[float]], list[int], list[int], list[float]]:
    scorer = PoiScoringService()
    rows: list[list[float]] = []
    labels: list[int] = []
    groups: list[int] = []
    baseline_scores: list[float] = []
    for query in SYNTH_QUERIES:
        group_size = 0
        for poi in pois:
            scoreable = _scoreable_poi(poi)
            breakdown = scorer.score_poi(scoreable, free_text=query["text"])
            rows.append(
                build_features(
                    scoreable,
                    breakdown,
                    distance_m=0,
                    ugc_sim=ugc_sim_from_match(breakdown.ugc_match),
                )
            )
            labels.append(_query_label(scoreable, query))
            baseline_scores.append(breakdown.total)
            group_size += 1
        if group_size:
            groups.append(group_size)
    return rows, labels, groups, baseline_scores


def _save_model(model: Any, model_out: Path) -> None:
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as temp_file:
        temp_path = Path(temp_file.name)
    try:
        model.save_model(str(temp_path))
        shutil.copyfile(temp_path, model_out)
    finally:
        temp_path.unlink(missing_ok=True)


def _scoreable_poi(poi: Any) -> Any:
    defaults = {
        "id": "",
        "category": "",
        "rating": 0.0,
        "review_count": 0,
        "queue_estimate": {"weekend_peak": 0},
        "price_per_person": None,
        "tags": [],
        "suitable_for": [],
        "atmosphere": [],
        "high_freq_keywords": [],
        "latitude": None,
        "longitude": None,
    }
    return SimpleNamespace(
        **{
            key: getattr(poi, key, value)
            for key, value in defaults.items()
        }
    )


def _query_label(poi: Any, query: dict[str, Any]) -> int:
    label = _base_label(poi)
    label += int(query.get("category_boost", {}).get(getattr(poi, "category", ""), 0))
    queue_min = (getattr(poi, "queue_estimate", {}) or {}).get("weekend_peak", 0)
    if query.get("avoid_queue") and queue_min <= 20:
        label += 2
    budget = query.get("budget")
    price = getattr(poi, "price_per_person", None)
    if budget is not None and price is not None:
        label += 2 if price <= budget else -2
    return max(0, min(label, 5))


def _base_label(poi: Any) -> int:
    label = 0
    if getattr(poi, "rating", 0) >= 4.5:
        label += 1
    if getattr(poi, "review_count", 0) >= 500:
        label += 1
    if getattr(poi, "category", "") in {"restaurant", "culture", "scenic"}:
        label += 1
    if (getattr(poi, "queue_estimate", {}) or {}).get("weekend_peak", 0) <= 25:
        label += 1
    return label


def _group_ndcg(labels: list[int], scores: list[float], groups: list[int], *, k: int = 5) -> float:
    if not groups:
        return 0.0
    total = 0.0
    offset = 0
    used = 0
    for group_size in groups:
        group_labels = labels[offset : offset + group_size]
        group_scores = scores[offset : offset + group_size]
        offset += group_size
        if not group_labels:
            continue
        ordered = [label for _, label in sorted(zip(group_scores, group_labels), reverse=True)]
        total += ndcg_at_k(ordered, k=k)
        used += 1
    return round(total / max(used, 1), 4)


if __name__ == "__main__":
    main()

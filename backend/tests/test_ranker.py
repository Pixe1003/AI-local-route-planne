from pathlib import Path
from types import SimpleNamespace
import importlib.util

from app.ml.features import FEATURE_ORDER, build_features, ugc_sim_from_match
from app.ml.ranker import PoiRanker, ndcg_at_k, should_enable_ranker
from app.schemas.plan import ScoreBreakdown


def test_ranker_feature_order_and_missing_model_fallback_are_stable(tmp_path: Path) -> None:
    poi = SimpleNamespace(
        queue_estimate={"weekend_peak": 18},
        price_per_person=55,
        review_count=1200,
    )
    breakdown = ScoreBreakdown(
        user_interest=20,
        poi_quality=25,
        context_fit=15,
        ugc_match=12,
        service_closure=8,
        history_preference=6,
        fact_alignment=4,
        queue_penalty=-3,
        price_penalty=-2,
        distance_penalty=-1,
        risk_penalty=0,
        total=84,
    )

    features = build_features(
        poi,
        breakdown,
        distance_m=800,
        ugc_sim=0.7,
    )

    assert FEATURE_ORDER == [
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
    assert len(features) == len(FEATURE_ORDER)
    assert features[FEATURE_ORDER.index("queue_min")] == 18
    assert PoiRanker(tmp_path / "missing.txt").predict(features) is None


def test_ranker_gate_requires_measurable_ndcg_lift() -> None:
    assert ndcg_at_k([3, 2, 0], k=3) == 1.0
    assert should_enable_ranker(model_ndcg=0.82, baseline_ndcg=0.80) is False
    assert should_enable_ranker(model_ndcg=0.85, baseline_ndcg=0.80) is True


def test_ranker_feature_context_reuses_online_ugc_mapping() -> None:
    assert ugc_sim_from_match(6.0) == 0.0
    assert ugc_sim_from_match(11.0) == 0.5
    assert ugc_sim_from_match(30.0) == 1.0


def test_ranker_training_dataset_uses_multiple_query_groups(monkeypatch) -> None:
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "train_ranker.py"
    spec = importlib.util.spec_from_file_location("train_ranker_module", module_path)
    train_ranker = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(train_ranker)

    pois = [
        SimpleNamespace(id="r", category="restaurant", rating=4.7, review_count=800, queue_estimate={"weekend_peak": 15}, price_per_person=60),
        SimpleNamespace(id="c", category="culture", rating=4.6, review_count=600, queue_estimate={"weekend_peak": 20}, price_per_person=30),
        SimpleNamespace(id="n", category="nightlife", rating=4.4, review_count=400, queue_estimate={"weekend_peak": 30}, price_per_person=80),
    ]

    rows, labels, groups, baseline_scores = train_ranker._build_dataset(pois)

    assert len(groups) >= 3
    assert all(group == len(pois) for group in groups)
    assert len(rows) == len(labels) == len(baseline_scores) == sum(groups)
    assert all(len(row) == len(FEATURE_ORDER) for row in rows)

from app.solver.optw import OptwNode
from app.solver.pareto import build_pareto_variants, dominates


def _nodes() -> list[OptwNode]:
    return [
        OptwNode("premium", "restaurant", utility=100, visit_min=20, price=80, open_min=540, close_min=780, queue_min=35),
        OptwNode("fast", "culture", utility=70, visit_min=20, price=20, open_min=540, close_min=780, queue_min=5),
        OptwNode("cheap", "cafe", utility=60, visit_min=20, price=5, open_min=540, close_min=780, queue_min=10),
        OptwNode("balanced", "scenic", utility=75, visit_min=20, price=30, open_min=540, close_min=780, queue_min=15),
    ]


def test_pareto_variants_are_non_dominated_and_distinct() -> None:
    variants = build_pareto_variants(
        _nodes(),
        {("premium", "fast"): 20, ("fast", "cheap"): 10, ("cheap", "balanced"): 10},
        solve_kwargs={
            "start_min": 540,
            "end_min": 720,
            "budget": 120,
            "must_visit": set(),
            "required_categories": set(),
            "required_category_groups": [],
            "max_stops": 3,
            "time_limit_seconds": 1,
            "solver_mode": "optw",
        },
    )

    assert len({tuple(variant.ordered_ids) for variant in variants}) >= 3
    metrics = [variant.metrics for variant in variants]
    assert not any(
        dominates(left, right)
        for index, left in enumerate(metrics)
        for right in metrics[index + 1 :]
    )

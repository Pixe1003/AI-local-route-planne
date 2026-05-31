import threading
import time

from app.solver.optw import OptwNode, OptwResult
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


def test_pareto_weight_profiles_solve_in_parallel(monkeypatch) -> None:
    nodes = [
        OptwNode(f"node_{index}", "scenic", utility=10, visit_min=10, price=10, open_min=540, close_min=780)
        for index in range(5)
    ]
    active = 0
    max_active = 0
    lock = threading.Lock()
    selected_index = {
        tuple(sorted(weights.items())): index
        for index, (_, weights) in enumerate(
            [
                ("interest", {"utility": 1.0, "time": 0.0, "cost": 0.0, "queue": 0.0}),
                ("balanced", {"utility": 1.0, "time": 0.2, "cost": 0.25, "queue": 0.25}),
                ("time_saving", {"utility": 0.8, "time": 0.7, "cost": 0.05, "queue": 0.1}),
                ("budget_saving", {"utility": 0.8, "time": 0.05, "cost": 0.8, "queue": 0.1}),
                ("low_queue", {"utility": 0.8, "time": 0.05, "cost": 0.1, "queue": 0.8}),
            ]
        )
    }

    def fake_solve_optw(*args, **kwargs) -> OptwResult:
        nonlocal active, max_active
        weights = kwargs["weights"]
        node_index = selected_index[tuple(sorted(weights.items()))]
        with lock:
            active += 1
            max_active = max(max_active, active)
        try:
            time.sleep(0.05)
            return OptwResult(
                ordered_ids=[f"node_{node_index}"],
                solver="fake",
                objective_value=1.0,
                selected_utility=10,
                total_duration_min=10,
                total_cost=10,
            )
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr("app.solver.pareto.solve_optw", fake_solve_optw)

    variants = build_pareto_variants(
        nodes,
        {},
        solve_kwargs={
            "start_min": 540,
            "end_min": 720,
            "budget": 100,
            "must_visit": set(),
            "required_categories": set(),
            "required_category_groups": [],
            "max_stops": 1,
            "time_limit_seconds": 1,
            "solver_mode": "optw",
        },
    )

    assert [variant.label for variant in variants[:5]] == [
        "interest",
        "balanced",
        "time_saving",
        "budget_saving",
        "low_queue",
    ]
    assert max_active > 1

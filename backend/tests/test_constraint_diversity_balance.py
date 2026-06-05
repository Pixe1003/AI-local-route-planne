from types import SimpleNamespace

from app.schemas.plan import HardConstraints, RouteMetrics, RouteSkeleton, RouteStop, SoftPreferences, StructuredIntent
from app.services.route_validator import RouteValidator
from app.solver.optw import OptwNode
from app.solver.pareto import build_pareto_variants
from eval.metrics import EvalResult, aggregate


def _route(*poi_ids: str, total_cost: int = 180) -> RouteSkeleton:
    return RouteSkeleton(
        style="story",
        stops=[
            RouteStop(poi_id=poi_id, arrival_time="10:00", departure_time="10:30", duration_min=30)
            for poi_id in poi_ids
        ],
        dropped_poi_ids=[],
        drop_reasons={},
        metrics=RouteMetrics(
            total_duration_min=90,
            total_cost=total_cost,
            poi_count=len(poi_ids),
            walking_distance_meters=0,
            queue_total_min=0,
        ),
    )


def _intent(*, strict_budget: bool = False, avoid_pois: list[str] | None = None) -> StructuredIntent:
    return StructuredIntent(
        hard_constraints=HardConstraints(
            start_time="09:00",
            end_time="12:00",
            budget_total=100,
            strict_budget=strict_budget,
            must_include_experience=False,
        ),
        soft_preferences=SoftPreferences(),
        must_visit_pois=[],
        avoid_pois=avoid_pois or [],
    )


def test_budget_is_soft_guardrail_unless_user_makes_it_strict() -> None:
    validator = RouteValidator(repo=_Repo(["r", "c", "m"]))

    soft = validator.validate(_route("r", "c", "m", total_cost=140), _intent(strict_budget=False))
    strict = validator.validate(_route("r", "c", "m", total_cost=140), _intent(strict_budget=True))

    assert soft.is_valid is True
    assert [issue.code for issue in soft.issues] == ["budget_exceeded"]
    assert soft.issues[0].severity == "warning"
    assert strict.is_valid is False
    assert strict.issues[0].severity == "error"


def test_explicitly_avoided_pois_are_hard_constraints() -> None:
    validation = RouteValidator(repo=_Repo(["restaurant", "blocked", "museum"])).validate(
        _route("restaurant", "blocked", "museum"),
        _intent(avoid_pois=["blocked"]),
    )

    assert validation.is_valid is False
    assert "avoided_poi_included" in [issue.code for issue in validation.issues]


def test_pareto_variants_have_business_labels_and_are_filtered_for_overlap() -> None:
    nodes = [
        OptwNode("food", "restaurant", utility=100, visit_min=20, price=80, open_min=540, close_min=780, queue_min=30),
        OptwNode("museum", "culture", utility=80, visit_min=20, price=20, open_min=540, close_min=780, queue_min=5),
        OptwNode("cafe", "cafe", utility=75, visit_min=20, price=25, open_min=540, close_min=780, queue_min=8),
        OptwNode("mall", "shopping", utility=70, visit_min=20, price=40, open_min=540, close_min=780, queue_min=6),
        OptwNode("park", "outdoor", utility=68, visit_min=20, price=0, open_min=540, close_min=780, queue_min=0),
    ]
    variants = build_pareto_variants(
        nodes,
        {("food", "museum"): 10, ("museum", "cafe"): 10, ("cafe", "mall"): 10, ("mall", "park"): 10},
        solve_kwargs={
            "start_min": 540,
            "end_min": 720,
            "budget": None,
            "must_visit": set(),
            "required_categories": set(),
            "required_category_groups": [],
            "max_stops": 3,
            "time_limit_seconds": 1,
            "solver_mode": "optw",
        },
    )

    assert len(variants) >= 3
    assert all(variant.business_label for variant in variants)
    assert all(variant.tradeoff_reason for variant in variants)
    assert all(0 <= variant.diversity_score <= 1 for variant in variants)
    assert _avg_jaccard([variant.ordered_ids for variant in variants]) <= 0.8


def test_eval_aggregate_includes_business_diversity_metrics() -> None:
    summary = aggregate(
        [
            EvalResult(
                scenario_id="a",
                feasible=True,
                constraints_satisfied=True,
                explanation_faithfulness=1.0,
                variant_jaccard_overlap=0.5,
                category_entropy=1.1,
                business_area_spread=0.7,
                soft_constraint_tradeoff_score=0.9,
                scenario_expectation_passed=True,
            ),
            EvalResult(
                scenario_id="b",
                feasible=True,
                constraints_satisfied=True,
                explanation_faithfulness=1.0,
                variant_jaccard_overlap=0.7,
                category_entropy=0.9,
                business_area_spread=0.5,
                soft_constraint_tradeoff_score=0.8,
                scenario_expectation_passed=False,
            ),
        ]
    )

    assert summary["avg_variant_jaccard_overlap"] == 0.6
    assert summary["avg_category_entropy"] == 1.0
    assert summary["avg_business_area_spread"] == 0.6
    assert summary["avg_soft_constraint_tradeoff_score"] == 0.85
    assert summary["scenario_expectation_pass_rate"] == 0.5


def _avg_jaccard(routes: list[list[str]]) -> float:
    overlaps = []
    for index, left in enumerate(routes):
        for right in routes[index + 1 :]:
            left_set = set(left)
            right_set = set(right)
            overlaps.append(len(left_set & right_set) / max(len(left_set | right_set), 1))
    return sum(overlaps) / max(len(overlaps), 1)


class _EmptyRepo:
    def get_many(self, poi_ids):
        return []

    def list_by_city(self, city):
        return []


class _Repo:
    def __init__(self, poi_ids: list[str]) -> None:
        self._pois = {
            poi_id: SimpleNamespace(
                id=poi_id,
                name=poi_id,
                category="cafe",
                open_hours={},
                queue_estimate={"weekend_peak": 0},
            )
            for poi_id in poi_ids
        }

    def get_many(self, poi_ids):
        return [self._pois[poi_id] for poi_id in poi_ids if poi_id in self._pois]

    def list_by_city(self, city):
        return list(self._pois.values())

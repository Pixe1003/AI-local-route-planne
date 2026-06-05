from types import SimpleNamespace
from pathlib import Path

from app.agent.story_models import StoryPlan, StoryStop
from eval.metrics import EvalResult, aggregate, explanation_faithfulness
from eval.run_eval import _render_report, _scenario_expectation_passed


def test_explanation_faithfulness_rewards_grounded_claims_and_rejects_mismatches() -> None:
    poi_by_id = {
        "p1": SimpleNamespace(
            category="restaurant",
            rating=4.8,
            high_freq_keywords=[{"keyword": "local food"}, {"keyword": "low queue"}],
        )
    }
    grounded = StoryPlan(
        theme="food",
        narrative="grounded",
        stops=[
            StoryStop(
                poi_id="p1",
                role="main",
                why="Chosen as restaurant with rating 4.8; UGC mentions local food and low queue.",
                ugc_quote_ref="pool:p1",
                ugc_quote="local food",
            )
        ],
    )
    mismatched = grounded.model_copy(deep=True)
    mismatched.stops[0].why = "Chosen for nightlife and river views."

    assert explanation_faithfulness(grounded, poi_by_id) == 1.0
    assert explanation_faithfulness(mismatched, poi_by_id) == 0.0


def test_eval_aggregate_includes_route_gap_and_ndcg() -> None:
    summary = aggregate(
        [
            EvalResult(
                scenario_id="a",
                feasible=True,
                constraints_satisfied=True,
                explanation_faithfulness=1.0,
                route_quality_gap=0.05,
                ndcg_at_5=0.8,
            ),
            EvalResult(
                scenario_id="b",
                feasible=True,
                constraints_satisfied=False,
                explanation_faithfulness=0.5,
                route_quality_gap=0.15,
                ndcg_at_5=0.6,
            ),
        ]
    )

    assert summary["avg_route_quality_gap"] == 0.1
    assert summary["avg_ndcg_at_5"] == 0.7


def test_eval_report_is_rendered_in_chinese() -> None:
    report = _render_report(
        [
            EvalResult(
                scenario_id="budget_tight",
                feasible=True,
                constraints_satisfied=True,
                explanation_faithfulness=1.0,
                route_quality_gap=0.05,
                ndcg_at_5=0.8,
                route_variant_count=5,
                on_time_prob=0.9,
                variant_jaccard_overlap=0.4,
                category_entropy=1.1,
                scenario_expectation_passed=True,
            )
        ]
    )

    assert "# AIroute 离线评估报告" in report
    assert "## 汇总指标" in report
    assert "## 门禁结果" in report
    assert "CI 门禁状态" in report
    assert "| 场景说明 | ID | 可行 | 约束满足 | 解释忠实度 |" in report
    assert "| 低预算半日路线：80 元内、本地菜、避免高价点 | budget_tight | 是 | 是 |" in report
    assert "## Summary" not in report
    assert "| Scenario | Feasible | Constraints |" not in report


def test_eval_scenarios_cover_required_cases() -> None:
    scenario_dir = Path(__file__).resolve().parents[1] / "eval" / "scenarios"
    scenario_ids = {path.stem for path in scenario_dir.glob("*.yaml")}

    assert {
        "half_day_food",
        "budget_tight",
        "must_visit",
        "low_queue",
        "family_rainy",
        "food_interleave_guardrail",
        "hot_budget_indoor",
        "photo_cafe_culture",
        "rainy_parent_child_short",
        "shopping_dinner_evening",
    } <= scenario_ids


def test_scenario_expectation_checks_dining_rhythm_and_subcategory_diversity() -> None:
    scenario = {
        "request": {},
        "expected": {
            "max_restaurant_count": 2,
            "min_non_restaurant_count": 2,
            "no_adjacent_restaurants": True,
            "unique_restaurant_subcategories": True,
        },
    }
    good = [
        SimpleNamespace(category="restaurant", sub_category="快餐厅", latitude=31.0, longitude=117.0),
        SimpleNamespace(category="scenic", sub_category="公园", latitude=31.001, longitude=117.001),
        SimpleNamespace(category="culture", sub_category="茶艺馆", latitude=31.002, longitude=117.002),
        SimpleNamespace(category="restaurant", sub_category="中餐厅", latitude=31.003, longitude=117.003),
    ]
    bad = [
        SimpleNamespace(category="restaurant", sub_category="快餐厅", latitude=31.0, longitude=117.0),
        SimpleNamespace(category="restaurant", sub_category="快餐厅", latitude=31.001, longitude=117.001),
        SimpleNamespace(category="scenic", sub_category="公园", latitude=31.002, longitude=117.002),
        SimpleNamespace(category="restaurant", sub_category="中餐厅", latitude=31.003, longitude=117.003),
    ]

    assert _scenario_expectation_passed({}, scenario, good, variant_overlap=None, category_entropy=None) is True
    assert _scenario_expectation_passed({}, scenario, bad, variant_overlap=None, category_entropy=None) is False


def test_scenario_expectation_checks_straight_line_route_distance() -> None:
    scenario = {
        "request": {},
        "expected": {
            "max_straight_segment_m": 500,
            "max_straight_total_m": 800,
        },
    }
    compact = [
        SimpleNamespace(category="restaurant", latitude=31.0, longitude=117.0),
        SimpleNamespace(category="culture", latitude=31.001, longitude=117.001),
        SimpleNamespace(category="restaurant", latitude=31.002, longitude=117.002),
    ]
    far = [
        SimpleNamespace(category="restaurant", latitude=31.0, longitude=117.0),
        SimpleNamespace(category="culture", latitude=31.2, longitude=117.2),
        SimpleNamespace(category="restaurant", latitude=31.4, longitude=117.4),
    ]

    assert _scenario_expectation_passed({}, scenario, compact, variant_overlap=None, category_entropy=None) is True
    assert _scenario_expectation_passed({}, scenario, far, variant_overlap=None, category_entropy=None) is False

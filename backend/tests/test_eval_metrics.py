from types import SimpleNamespace
from pathlib import Path

from app.agent.story_models import StoryPlan, StoryStop
from eval.metrics import EvalResult, aggregate, explanation_faithfulness


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


def test_eval_scenarios_cover_required_cases() -> None:
    scenario_dir = Path(__file__).resolve().parents[1] / "eval" / "scenarios"
    scenario_ids = {path.stem for path in scenario_dir.glob("*.yaml")}

    assert {
        "half_day_food",
        "budget_tight",
        "must_visit",
        "low_queue",
        "family_rainy",
    } <= scenario_ids

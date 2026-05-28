from app.solver.optw import OptwNode, solve_optw


def test_cp_sat_optw_matches_small_exact_solution_and_respects_constraints() -> None:
    nodes = [
        OptwNode(
            poi_id="restaurant",
            category="restaurant",
            utility=10,
            visit_min=20,
            price=30,
            open_min=540,
            close_min=720,
        ),
        OptwNode(
            poi_id="museum",
            category="culture",
            utility=8,
            visit_min=20,
            price=20,
            open_min=540,
            close_min=720,
        ),
        OptwNode(
            poi_id="cafe",
            category="cafe",
            utility=7,
            visit_min=20,
            price=10,
            open_min=540,
            close_min=720,
        ),
        OptwNode(
            poi_id="expensive_closed",
            category="scenic",
            utility=50,
            visit_min=20,
            price=90,
            open_min=700,
            close_min=720,
        ),
    ]
    travel = {
        ("restaurant", "museum"): 10,
        ("museum", "restaurant"): 10,
        ("museum", "cafe"): 10,
        ("cafe", "museum"): 10,
        ("restaurant", "cafe"): 60,
        ("cafe", "restaurant"): 60,
        ("restaurant", "expensive_closed"): 5,
        ("expensive_closed", "restaurant"): 5,
        ("museum", "expensive_closed"): 5,
        ("expensive_closed", "museum"): 5,
        ("cafe", "expensive_closed"): 5,
        ("expensive_closed", "cafe"): 5,
    }

    result = solve_optw(
        nodes,
        travel,
        start_min=540,
        end_min=660,
        budget=60,
        must_visit={"museum"},
        required_categories={"restaurant"},
        max_stops=3,
        time_limit_seconds=2,
        solver_mode="optw",
    )

    assert result.ordered_ids == ["restaurant", "museum", "cafe"]
    assert result.selected_utility == 25
    assert result.total_cost == 60
    assert result.constraint_violations == []
    assert result.optimality_gap == 0
    assert result.solver.startswith("cp_sat")
    assert result.fallback_used is False


def test_optw_reports_fallback_when_hard_constraints_are_infeasible() -> None:
    nodes = [
        OptwNode(
            poi_id="must",
            category="culture",
            utility=8,
            visit_min=45,
            price=20,
            open_min=540,
            close_min=550,
        )
    ]

    result = solve_optw(
        nodes,
        {},
        start_min=540,
        end_min=600,
        budget=30,
        must_visit={"must"},
        max_stops=1,
        time_limit_seconds=1,
        solver_mode="optw",
    )

    assert result.ordered_ids == ["must"]
    assert "infeasible_constraints" in result.constraint_violations
    assert result.fallback_used is True

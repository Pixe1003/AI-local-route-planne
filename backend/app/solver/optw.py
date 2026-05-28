from __future__ import annotations

from dataclasses import dataclass, field
from itertools import permutations
from math import ceil
from typing import Any, Iterable


@dataclass(frozen=True)
class OptwNode:
    poi_id: str
    category: str
    utility: float
    visit_min: int
    price: int
    open_min: int
    close_min: int
    queue_min: int = 0


@dataclass
class OptwResult:
    ordered_ids: list[str]
    solver: str
    objective_value: float
    selected_utility: float
    total_duration_min: int
    total_cost: int
    constraint_violations: list[str] = field(default_factory=list)
    optimality_gap: float | None = None
    fallback_used: bool = False


def solve_optw(
    nodes: list[OptwNode],
    travel_minutes: dict[tuple[str, str], int],
    *,
    start_min: int,
    end_min: int,
    budget: int | None = None,
    must_visit: set[str] | None = None,
    required_categories: set[str] | None = None,
    required_category_groups: list[set[str]] | None = None,
    max_stops: int = 5,
    time_limit_seconds: float = 3.0,
    solver_mode: str = "optw",
    weights: dict[str, float] | None = None,
) -> OptwResult:
    if not nodes:
        return OptwResult(
            ordered_ids=[],
            solver="empty",
            objective_value=0,
            selected_utility=0,
            total_duration_min=0,
            total_cost=0,
            fallback_used=True,
            constraint_violations=["no_candidates"],
        )

    must_visit = must_visit or set()
    required_categories = required_categories or set()
    required_category_groups = required_category_groups or []
    objective_weights = _normalize_weights(weights)

    if solver_mode == "exact":
        return _exact_search(
            nodes,
            travel_minutes,
            start_min=start_min,
            end_min=end_min,
            budget=budget,
            must_visit=must_visit,
            required_categories=required_categories,
            required_category_groups=required_category_groups,
            max_stops=max_stops,
            weights=objective_weights,
        )

    if solver_mode == "greedy" or len(nodes) > 15:
        return _greedy_fallback(
            nodes,
            travel_minutes,
            start_min=start_min,
            end_min=end_min,
            budget=budget,
            must_visit=must_visit,
            required_categories=required_categories,
            required_category_groups=required_category_groups,
            max_stops=max_stops,
            weights=objective_weights,
            reason="greedy_mode" if solver_mode == "greedy" else "candidate_limit",
        )

    try:
        from ortools.sat.python import cp_model
    except Exception:
        exact = _exact_search(
            nodes,
            travel_minutes,
            start_min=start_min,
            end_min=end_min,
            budget=budget,
            must_visit=must_visit,
            required_categories=required_categories,
            required_category_groups=required_category_groups,
            max_stops=max_stops,
            weights=objective_weights,
        )
        exact.solver = "cp_sat_unavailable_exact"
        return exact

    cp: Any = cp_model
    model: Any = cp.CpModel()
    count = len(nodes)
    start = 0
    end = count + 1
    node_index = {i + 1: node for i, node in enumerate(nodes)}
    x = {i: model.NewBoolVar(f"x_{i}") for i in range(1, count + 1)}
    y: dict[tuple[int, int], Any] = {}

    from_nodes = [start, *range(1, count + 1)]
    to_nodes = [*range(1, count + 1), end]
    for i in from_nodes:
        for j in to_nodes:
            if i == j:
                continue
            y[(i, j)] = model.NewBoolVar(f"y_{i}_{j}")

    model.Add(sum(y[(start, j)] for j in range(1, count + 1)) == 1)
    model.Add(sum(y[(i, end)] for i in range(1, count + 1)) == 1)
    for i in range(1, count + 1):
        model.Add(sum(y[(j, i)] for j in from_nodes if j != i) == x[i])
        model.Add(sum(y[(i, j)] for j in to_nodes if j != i) == x[i])

    model.Add(sum(x.values()) <= max_stops)
    for i, node in node_index.items():
        if node.poi_id in must_visit:
            model.Add(x[i] == 1)
    for category in required_categories:
        model.Add(sum(x[i] for i, node in node_index.items() if node.category == category) >= 1)
    for group_index, categories in enumerate(required_category_groups):
        model.Add(
            sum(x[i] for i, node in node_index.items() if node.category in categories) >= 1
        ).WithName(f"required_category_group_{group_index}")
    if budget is not None:
        model.Add(sum(node_index[i].price * x[i] for i in range(1, count + 1)) <= budget)

    t = {
        i: model.NewIntVar(start_min, end_min, f"t_{i}")
        for i in range(1, count + 1)
    }
    t_end = model.NewIntVar(start_min, end_min, "t_end")
    for i, node in node_index.items():
        model.Add(t[i] >= node.open_min).OnlyEnforceIf(x[i])
        model.Add(t[i] + node.visit_min <= node.close_min).OnlyEnforceIf(x[i])
        model.Add(t[i] + node.visit_min <= end_min).OnlyEnforceIf(x[i])

    for (i, j), arc in y.items():
        if i == start and j != end:
            model.Add(t[j] >= start_min).OnlyEnforceIf(arc)
            continue
        if j == end and i != start:
            model.Add(t_end >= t[i] + node_index[i].visit_min).OnlyEnforceIf(arc)
            continue
        if i != start and j != end:
            model.Add(
                t[j]
                >= t[i]
                + node_index[i].visit_min
                + _travel(node_index[i].poi_id, node_index[j].poi_id, travel_minutes)
            ).OnlyEnforceIf(arc)

    model.Maximize(
        sum(int(round(_node_score(node_index[i], objective_weights) * 100)) * x[i] for i in range(1, count + 1))
        - int(round(objective_weights["time"] * 100)) * (t_end - start_min)
    )
    solver: Any = cp.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_seconds)
    status = solver.Solve(model)

    if status not in {cp.OPTIMAL, cp.FEASIBLE}:
        return _greedy_fallback(
            nodes,
            travel_minutes,
            start_min=start_min,
            end_min=end_min,
            budget=budget,
            must_visit=must_visit,
            required_categories=required_categories,
            required_category_groups=required_category_groups,
            max_stops=max_stops,
            weights=objective_weights,
            reason="infeasible_constraints",
        )

    order: list[str] = []
    current = start
    for _ in range(count + 1):
        next_index = next(
            (
                j
                for j in to_nodes
                if (current, j) in y and solver.BooleanValue(y[(current, j)])
            ),
            end,
        )
        if next_index == end:
            break
        order.append(node_index[next_index].poi_id)
        current = next_index

    by_id = {node.poi_id: node for node in nodes}
    selected_ids = set(order)
    order = _best_order_for_selected(
        [node for node in nodes if node.poi_id in selected_ids],
        travel_minutes,
        start_min=start_min,
        end_min=end_min,
    )
    selected = [by_id[poi_id] for poi_id in order]
    objective = _objective_for_ids(order, by_id, travel_minutes, start_min, objective_weights)
    selected_utility = sum(node.utility for node in selected)
    best_bound = float(solver.BestObjectiveBound()) / 100 if solver.BestObjectiveBound() else objective
    gap = 0.0 if status == cp_model.OPTIMAL or best_bound <= 0 else round((best_bound - objective) / best_bound, 4)
    return OptwResult(
        ordered_ids=order,
        solver="cp_sat_optimal" if status == cp.OPTIMAL else "cp_sat_feasible",
        objective_value=objective,
        selected_utility=selected_utility,
        total_duration_min=_duration(order, by_id, travel_minutes, start_min),
        total_cost=sum(node.price for node in selected),
        optimality_gap=gap,
        fallback_used=False,
    )


def _exact_search(
    nodes: list[OptwNode],
    travel_minutes: dict[tuple[str, str], int],
    *,
    start_min: int,
    end_min: int,
    budget: int | None,
    must_visit: set[str],
    required_categories: set[str],
    required_category_groups: list[set[str]],
    max_stops: int,
    weights: dict[str, float],
) -> OptwResult:
    best_order: tuple[OptwNode, ...] = ()
    best_objective = float("-inf")
    for size in range(1, min(max_stops, len(nodes)) + 1):
        for order in permutations(nodes, size):
            if not _order_satisfies(
                order,
                travel_minutes,
                start_min=start_min,
                end_min=end_min,
                budget=budget,
                must_visit=must_visit,
                required_categories=required_categories,
                required_category_groups=required_category_groups,
            ):
                continue
            ordered_ids = [node.poi_id for node in order]
            objective = _objective_for_ids(
                ordered_ids,
                {node.poi_id: node for node in nodes},
                travel_minutes,
                start_min,
                weights,
            )
            if objective > best_objective:
                best_order = order
                best_objective = objective
    if not best_order:
        return _greedy_fallback(
            nodes,
            travel_minutes,
            start_min=start_min,
            end_min=end_min,
            budget=budget,
            must_visit=must_visit,
            required_categories=required_categories,
            required_category_groups=required_category_groups,
            max_stops=max_stops,
            weights=weights,
            reason="infeasible_constraints",
        )
    ordered_ids = [node.poi_id for node in best_order]
    return OptwResult(
        ordered_ids=ordered_ids,
        solver="exact",
        objective_value=best_objective,
        selected_utility=sum(node.utility for node in best_order),
        total_duration_min=_duration(ordered_ids, {node.poi_id: node for node in nodes}, travel_minutes, start_min),
        total_cost=sum(node.price for node in best_order),
        optimality_gap=0.0,
    )


def _order_satisfies(
    order: Iterable[OptwNode],
    travel_minutes: dict[tuple[str, str], int],
    *,
    start_min: int,
    end_min: int,
    budget: int | None,
    must_visit: set[str],
    required_categories: set[str],
    required_category_groups: list[set[str]],
) -> bool:
    ordered = list(order)
    ids = {node.poi_id for node in ordered}
    categories = {node.category for node in ordered}
    if not must_visit <= ids:
        return False
    if not required_categories <= categories:
        return False
    if any(not (categories & group) for group in required_category_groups):
        return False
    if budget is not None and sum(node.price for node in ordered) > budget:
        return False
    current = start_min
    previous: OptwNode | None = None
    for node in ordered:
        if previous is not None:
            current += _travel(previous.poi_id, node.poi_id, travel_minutes)
        current = max(current, node.open_min)
        if current + node.visit_min > node.close_min:
            return False
        current += node.visit_min
    return current <= end_min


def _best_order_for_selected(
    selected: list[OptwNode],
    travel_minutes: dict[tuple[str, str], int],
    *,
    start_min: int,
    end_min: int,
) -> list[str]:
    if len(selected) <= 1:
        return [node.poi_id for node in selected]
    best_order = selected
    best_duration: int | None = None
    for order in permutations(selected, len(selected)):
        if not _order_satisfies(
            order,
            travel_minutes,
            start_min=start_min,
            end_min=end_min,
            budget=None,
            must_visit=set(),
            required_categories=set(),
            required_category_groups=[],
        ):
            continue
        ordered_ids = [node.poi_id for node in order]
        duration = _duration(ordered_ids, {node.poi_id: node for node in selected}, travel_minutes, start_min)
        if best_duration is None or duration < best_duration:
            best_order = list(order)
            best_duration = duration
    return [node.poi_id for node in best_order]


def _greedy_fallback(
    nodes: list[OptwNode],
    travel_minutes: dict[tuple[str, str], int],
    *,
    start_min: int,
    end_min: int,
    budget: int | None,
    must_visit: set[str],
    required_categories: set[str],
    required_category_groups: list[set[str]],
    max_stops: int,
    weights: dict[str, float],
    reason: str,
) -> OptwResult:
    selected: list[OptwNode] = []
    by_id = {node.poi_id: node for node in nodes}
    for poi_id in must_visit:
        if poi_id in by_id:
            selected.append(by_id[poi_id])
    for category in required_categories:
        if not any(node.category == category for node in selected):
            match = _best(nodes, exclude=selected, categories={category}, weights=weights)
            if match:
                selected.append(match)
    for group in required_category_groups:
        if not any(node.category in group for node in selected):
            match = _best(nodes, exclude=selected, categories=group, weights=weights)
            if match:
                selected.append(match)
    for node in sorted(nodes, key=lambda item: _node_score(item, weights), reverse=True):
        if len(selected) >= max_stops:
            break
        if node not in selected:
            selected.append(node)
    selected = selected[:max_stops]
    ordered_ids = [node.poi_id for node in selected]
    violations = [reason]
    if not _order_satisfies(
        selected,
        travel_minutes,
        start_min=start_min,
        end_min=end_min,
        budget=budget,
        must_visit=must_visit,
        required_categories=required_categories,
        required_category_groups=required_category_groups,
    ):
        violations = list(dict.fromkeys([*violations, "infeasible_constraints"]))
    return OptwResult(
        ordered_ids=ordered_ids,
        solver="greedy_fallback",
        objective_value=_objective_for_ids(ordered_ids, by_id, travel_minutes, start_min, weights),
        selected_utility=sum(node.utility for node in selected),
        total_duration_min=_duration(ordered_ids, by_id, travel_minutes, start_min),
        total_cost=sum(node.price for node in selected),
        constraint_violations=violations,
        fallback_used=True,
    )


def _best(
    nodes: list[OptwNode],
    *,
    exclude: list[OptwNode],
    categories: set[str],
    weights: dict[str, float],
) -> OptwNode | None:
    excluded = {node.poi_id for node in exclude}
    matches = [node for node in nodes if node.category in categories and node.poi_id not in excluded]
    return max(matches, key=lambda node: _node_score(node, weights), default=None)


def _normalize_weights(weights: dict[str, float] | None) -> dict[str, float]:
    normalized = {"utility": 1.0, "time": 0.0, "cost": 0.0, "queue": 0.0}
    if weights:
        normalized.update({key: float(value) for key, value in weights.items() if key in normalized})
    return normalized


def _node_score(node: OptwNode, weights: dict[str, float]) -> float:
    return (
        weights["utility"] * node.utility
        - weights["cost"] * node.price
        - weights["queue"] * node.queue_min
    )


def _objective_for_ids(
    ordered_ids: list[str],
    by_id: dict[str, OptwNode],
    travel_minutes: dict[tuple[str, str], int],
    start_min: int,
    weights: dict[str, float],
) -> float:
    nodes = [by_id[poi_id] for poi_id in ordered_ids if poi_id in by_id]
    return round(
        sum(_node_score(node, weights) for node in nodes)
        - weights["time"] * _duration(ordered_ids, by_id, travel_minutes, start_min),
        4,
    )


def _duration(
    ordered_ids: list[str],
    by_id: dict[str, OptwNode],
    travel_minutes: dict[tuple[str, str], int],
    start_min: int,
) -> int:
    if not ordered_ids:
        return 0
    current = start_min
    previous_id: str | None = None
    for poi_id in ordered_ids:
        if previous_id is not None:
            current += _travel(previous_id, poi_id, travel_minutes)
        node = by_id[poi_id]
        current = max(current, node.open_min)
        current += node.visit_min
        previous_id = poi_id
    return current - start_min


def _travel(from_id: str, to_id: str, travel_minutes: dict[tuple[str, str], int]) -> int:
    return max(0, int(ceil(travel_minutes.get((from_id, to_id), travel_minutes.get((to_id, from_id), 0)))))

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
from math import ceil
from typing import Any

from app.solver.optw import OptwNode, OptwResult, solve_optw


@dataclass(frozen=True)
class RouteVariant:
    label: str
    ordered_ids: list[str]
    solver: str
    interest: float
    time_min: int
    cost: int
    queue_min: int
    objective_value: float
    non_dominated: bool = True

    @property
    def metrics(self) -> dict[str, float]:
        return {
            "interest": float(self.interest),
            "time": float(self.time_min),
            "cost": float(self.cost),
            "queue": float(self.queue_min),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "ordered_ids": self.ordered_ids,
            "solver": self.solver,
            "interest": self.interest,
            "time_min": self.time_min,
            "cost": self.cost,
            "queue_min": self.queue_min,
            "metrics": self.metrics,
            "objective_value": self.objective_value,
            "non_dominated": self.non_dominated,
            "dominated_by": [],
        }


WEIGHT_PROFILES: list[tuple[str, dict[str, float]]] = [
    ("interest", {"utility": 1.0, "time": 0.0, "cost": 0.0, "queue": 0.0}),
    ("balanced", {"utility": 1.0, "time": 0.2, "cost": 0.25, "queue": 0.25}),
    ("time_saving", {"utility": 0.8, "time": 0.7, "cost": 0.05, "queue": 0.1}),
    ("budget_saving", {"utility": 0.8, "time": 0.05, "cost": 0.8, "queue": 0.1}),
    ("low_queue", {"utility": 0.8, "time": 0.05, "cost": 0.1, "queue": 0.8}),
]


def build_pareto_variants(
    nodes: list[OptwNode],
    travel_minutes: dict[tuple[str, str], int],
    *,
    solve_kwargs: dict[str, Any],
    max_variants: int = 5,
) -> list[RouteVariant]:
    if not nodes:
        return []

    by_id = {node.poi_id: node for node in nodes}
    candidates: list[RouteVariant] = []
    for label, weights in WEIGHT_PROFILES:
        kwargs = {**solve_kwargs, "weights": weights}
        result = solve_optw(nodes, travel_minutes, **kwargs)
        _append_result(candidates, result, label, by_id, travel_minutes, int(solve_kwargs["start_min"]))

    if len(nodes) <= 8:
        candidates.extend(_enumerated_candidates(nodes, travel_minutes, solve_kwargs))
    else:
        candidates.extend(_heuristic_candidates(nodes, travel_minutes, solve_kwargs))

    deduped = _dedupe(candidates)
    frontier = _non_dominated(deduped)
    frontier.sort(key=lambda item: (-item.interest, item.cost, item.queue_min, item.time_min))
    return frontier[:max_variants]


def dominates(left: dict[str, float], right: dict[str, float]) -> bool:
    better_or_equal = (
        left["interest"] >= right["interest"]
        and left["time"] <= right["time"]
        and left["cost"] <= right["cost"]
        and left["queue"] <= right["queue"]
    )
    strictly_better = (
        left["interest"] > right["interest"]
        or left["time"] < right["time"]
        or left["cost"] < right["cost"]
        or left["queue"] < right["queue"]
    )
    return better_or_equal and strictly_better


def _append_result(
    variants: list[RouteVariant],
    result: OptwResult,
    label: str,
    by_id: dict[str, OptwNode],
    travel_minutes: dict[tuple[str, str], int],
    start_min: int,
) -> None:
    if not result.ordered_ids:
        return
    variants.append(
        _variant_from_ids(
            label,
            result.ordered_ids,
            result.solver,
            by_id,
            travel_minutes,
            start_min,
            result.objective_value,
        )
    )


def _enumerated_candidates(
    nodes: list[OptwNode],
    travel_minutes: dict[tuple[str, str], int],
    solve_kwargs: dict[str, Any],
) -> list[RouteVariant]:
    variants: list[RouteVariant] = []
    max_stops = min(int(solve_kwargs.get("max_stops", 5)), len(nodes))
    by_id = {node.poi_id: node for node in nodes}
    start_min = int(solve_kwargs["start_min"])
    for size in range(1, max_stops + 1):
        for order in permutations(nodes, size):
            if not _is_feasible(order, travel_minutes, solve_kwargs):
                continue
            ordered_ids = [node.poi_id for node in order]
            variants.append(
                _variant_from_ids(
                    "frontier",
                    ordered_ids,
                    "enumerated",
                    by_id,
                    travel_minutes,
                    start_min,
                    sum(node.utility for node in order),
                )
            )
    return variants


def _heuristic_candidates(
    nodes: list[OptwNode],
    travel_minutes: dict[tuple[str, str], int],
    solve_kwargs: dict[str, Any],
) -> list[RouteVariant]:
    variants: list[RouteVariant] = []
    max_stops = int(solve_kwargs.get("max_stops", 5))
    by_id = {node.poi_id: node for node in nodes}
    start_min = int(solve_kwargs["start_min"])
    profiles = [
        ("frontier_interest", sorted(nodes, key=lambda node: node.utility, reverse=True)),
        ("frontier_budget", sorted(nodes, key=lambda node: (node.price, -node.utility))),
        ("frontier_queue", sorted(nodes, key=lambda node: (node.queue_min, -node.utility))),
    ]
    for label, ordered_nodes in profiles:
        selected: list[OptwNode] = []
        for node in ordered_nodes:
            trial = [*selected, node]
            if len(trial) <= max_stops and _is_feasible(trial, travel_minutes, solve_kwargs):
                selected = trial
        if selected:
            ordered_ids = [node.poi_id for node in selected]
            variants.append(
                _variant_from_ids(
                    label,
                    ordered_ids,
                    "heuristic",
                    by_id,
                    travel_minutes,
                    start_min,
                    sum(node.utility for node in selected),
                )
            )
    return variants


def _dedupe(candidates: list[RouteVariant]) -> list[RouteVariant]:
    seen: set[tuple[str, ...]] = set()
    result: list[RouteVariant] = []
    for candidate in candidates:
        key = tuple(candidate.ordered_ids)
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def _non_dominated(candidates: list[RouteVariant]) -> list[RouteVariant]:
    result: list[RouteVariant] = []
    for candidate in candidates:
        if any(
            dominates(other.metrics, candidate.metrics)
            for other in candidates
            if tuple(other.ordered_ids) != tuple(candidate.ordered_ids)
        ):
            continue
        result.append(candidate)
    return result


def _variant_from_ids(
    label: str,
    ordered_ids: list[str],
    solver: str,
    by_id: dict[str, OptwNode],
    travel_minutes: dict[tuple[str, str], int],
    start_min: int,
    objective_value: float,
) -> RouteVariant:
    selected = [by_id[poi_id] for poi_id in ordered_ids if poi_id in by_id]
    return RouteVariant(
        label=label,
        ordered_ids=ordered_ids,
        solver=solver,
        interest=round(sum(node.utility for node in selected), 3),
        time_min=_duration(ordered_ids, by_id, travel_minutes, start_min),
        cost=sum(node.price for node in selected),
        queue_min=sum(node.queue_min for node in selected),
        objective_value=round(objective_value, 4),
    )


def _is_feasible(
    order: list[OptwNode] | tuple[OptwNode, ...],
    travel_minutes: dict[tuple[str, str], int],
    solve_kwargs: dict[str, Any],
) -> bool:
    ordered = list(order)
    ids = {node.poi_id for node in ordered}
    categories = {node.category for node in ordered}
    must_visit = set(solve_kwargs.get("must_visit") or set())
    required_categories = set(solve_kwargs.get("required_categories") or set())
    required_groups = list(solve_kwargs.get("required_category_groups") or [])
    budget = solve_kwargs.get("budget")
    if not must_visit <= ids:
        return False
    if not required_categories <= categories:
        return False
    if any(not (categories & set(group)) for group in required_groups):
        return False
    if budget is not None and sum(node.price for node in ordered) > int(budget):
        return False
    current = int(solve_kwargs["start_min"])
    end_min = int(solve_kwargs["end_min"])
    previous: OptwNode | None = None
    for node in ordered:
        if previous is not None:
            current += _travel(previous.poi_id, node.poi_id, travel_minutes)
        if current < node.open_min or current + node.visit_min > node.close_min:
            return False
        current += node.visit_min
        previous = node
    return current <= end_min


def _duration(
    ordered_ids: list[str],
    by_id: dict[str, OptwNode],
    travel_minutes: dict[tuple[str, str], int],
    start_min: int,
) -> int:
    current = start_min
    previous: str | None = None
    for poi_id in ordered_ids:
        if previous is not None:
            current += _travel(previous, poi_id, travel_minutes)
        current += by_id[poi_id].visit_min
        previous = poi_id
    return current - start_min


def _travel(from_id: str, to_id: str, travel_minutes: dict[tuple[str, str], int]) -> int:
    return max(0, int(ceil(travel_minutes.get((from_id, to_id), travel_minutes.get((to_id, from_id), 0)))))

"""Travel-time aware ordering of route stops.

The previous solver only ordered the "efficient" style geographically (a greedy
nearest-neighbour pass) while "relaxed" and "foodie_first" ordered purely by
queue/category and could zig-zag across the city. This module provides a shared
nearest-neighbour construction followed by a 2-opt local search that minimises
total inter-stop travel time, so every style produces a geographically sane
route. The first stop is treated as a fixed anchor, which lets callers preserve
each style's character (e.g. foodie_first starts at a restaurant) while still
optimising the order of everything after it.
"""

from typing import Optional, Sequence

from app.solver.distance import estimate_transport


def optimize_visit_order(pois: Sequence, *, start_id: Optional[str] = None, city: Optional[str] = None) -> list:
    items = list(pois)
    n = len(items)
    if n <= 2:
        return items

    duration = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                duration[i][j] = estimate_transport(items[i], items[j], city=city).duration_min

    start = 0
    if start_id is not None:
        start = next((idx for idx, poi in enumerate(items) if poi.id == start_id), 0)

    order = _nearest_neighbour(duration, start, n)
    order = _two_opt(duration, order)
    return [items[index] for index in order]


def _nearest_neighbour(duration: list[list[int]], start: int, n: int) -> list[int]:
    visited = [False] * n
    order = [start]
    visited[start] = True
    for _ in range(n - 1):
        last = order[-1]
        nxt = min(
            (j for j in range(n) if not visited[j]),
            key=lambda j: duration[last][j],
        )
        order.append(nxt)
        visited[nxt] = True
    return order


def _path_cost(duration: list[list[int]], order: list[int]) -> int:
    return sum(duration[order[i]][order[i + 1]] for i in range(len(order) - 1))


def _two_opt(duration: list[list[int]], order: list[int]) -> list[int]:
    best = order
    best_cost = _path_cost(duration, best)
    improved = True
    while improved:
        improved = False
        # i starts at 1 so the anchor (first stop) is never moved.
        for i in range(1, len(best) - 1):
            for k in range(i + 1, len(best)):
                candidate = best[:i] + best[i : k + 1][::-1] + best[k + 1 :]
                cost = _path_cost(duration, candidate)
                if cost < best_cost:
                    best, best_cost, improved = candidate, cost, True
    return best

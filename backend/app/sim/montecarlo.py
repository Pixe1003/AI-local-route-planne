from __future__ import annotations

import random

from app.agent.story_models import RobustnessSummary
from app.schemas.plan import RouteSkeleton
from app.utils.time_utils import minutes_between


def simulate(
    route: RouteSkeleton,
    queue_by_poi_id: dict[str, int],
    *,
    end_min: int,
    n: int = 500,
    seed: int = 42,
) -> RobustnessSummary:
    samples = max(1, int(n))
    rng = random.Random(seed)
    if not route.stops:
        return RobustnessSummary(
            on_time_prob=1.0,
            expected_overflow_min=0.0,
            p90_total_min=0.0,
            samples=samples,
        )

    start_min = minutes_between("00:00", route.stops[0].arrival_time)
    total_minutes: list[float] = []
    overflow_minutes: list[float] = []
    for _ in range(samples):
        current = float(start_min)
        for stop in route.stops:
            queue_mean = max(0, int(queue_by_poi_id.get(stop.poi_id, 0) or 0))
            queue_std = max(2.0, queue_mean * 0.25)
            dwell_std = max(3.0, stop.duration_min * 0.12)
            queue_min = max(0.0, rng.gauss(queue_mean, queue_std))
            dwell_min = max(1.0, rng.gauss(stop.duration_min, dwell_std))
            current += queue_min + dwell_min
            if stop.transport_to_next is not None:
                transport = stop.transport_to_next.duration_min
                current += max(1.0, rng.gauss(transport, max(2.0, transport * 0.2)))
        total = current - start_min
        overflow = max(0.0, current - end_min)
        total_minutes.append(total)
        overflow_minutes.append(overflow)

    total_minutes.sort()
    p90_index = min(len(total_minutes) - 1, int(round((len(total_minutes) - 1) * 0.9)))
    on_time = sum(overflow == 0 for overflow in overflow_minutes)
    return RobustnessSummary(
        on_time_prob=round(on_time / samples, 3),
        expected_overflow_min=round(sum(overflow_minutes) / samples, 2),
        p90_total_min=round(total_minutes[p90_index], 2),
        samples=samples,
    )

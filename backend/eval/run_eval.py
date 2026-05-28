from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient

from app.api import routes_route
from app.main import app
from app.ml.ranker import ndcg_at_k
from app.repositories.poi_repo import get_poi_repository
from app.services.amap.schemas import AmapRouteMode, AmapRouteResult, AmapRouteStep
from app.solver.optw import OptwNode, solve_optw
from app.utils.time_utils import minutes_between
from eval.metrics import EvalResult, aggregate, explanation_faithfulness


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AIroute offline route quality evaluation.")
    parser.add_argument("--out", default="../data/eval/route_eval.md")
    parser.add_argument("--mode", choices=["agent"], default="agent")
    parser.add_argument("--scenarios", default=str(Path(__file__).parent / "scenarios"))
    parser.add_argument("--enforce-gate", action="store_true")
    args = parser.parse_args()

    _patch_local_route_client()
    results = [_evaluate_scenario(item) for item in _load_scenarios(Path(args.scenarios))]
    report = _render_report(results)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"Wrote eval report to {output}")
    if args.enforce_gate and not _gate_passed(aggregate(results)):
        raise SystemExit("Eval quality gate failed; inspect the generated report.")


def _load_scenarios(path: Path) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    for file in sorted(path.glob("*")):
        if file.suffix.lower() in {".yaml", ".yml"}:
            scenarios.append(yaml.safe_load(file.read_text(encoding="utf-8")))
        elif file.suffix.lower() == ".json":
            scenarios.append(json.loads(file.read_text(encoding="utf-8")))
    return scenarios


def _evaluate_scenario(scenario: dict[str, Any]) -> EvalResult:
    client = TestClient(app)
    response = client.post("/api/agent/run", json=scenario["request"])
    if response.status_code != 200:
        return EvalResult(
            scenario_id=scenario["id"],
            feasible=False,
            constraints_satisfied=False,
            explanation_faithfulness=0.0,
        )
    payload = response.json()
    story = payload.get("story_plan") or {}
    repo = get_poi_repository()
    poi_by_id = {
        poi.id: poi
        for poi in repo.get_many([stop["poi_id"] for stop in story.get("stops", [])])
    }
    faithfulness = explanation_faithfulness(_DictStory(story), poi_by_id)
    validation = payload.get("validation") or {}
    steps = payload.get("steps") or []
    robustness = payload.get("robustness") or {}
    return EvalResult(
        scenario_id=scenario["id"],
        feasible=bool(payload.get("ordered_poi_ids")),
        constraints_satisfied=bool(validation.get("is_valid", False)),
        explanation_faithfulness=faithfulness,
        tool_count=len(steps),
        total_tokens=sum(int(step.get("tokens_used", 0) or 0) for step in steps),
        total_latency_ms=sum(int(step.get("latency_ms", 0) or 0) for step in steps),
        route_quality_gap=_route_quality_gap(payload, scenario),
        ndcg_at_5=_route_ndcg_at_5(payload),
        route_variant_count=len(payload.get("route_variants") or []),
        on_time_prob=robustness.get("on_time_prob"),
    )


def _render_report(results: list[EvalResult]) -> str:
    summary = aggregate(results)
    lines = [
        "# AIroute Offline Eval",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {key} | {value} |" for key, value in summary.items())
    lines.extend(
        [
            "",
            "## Gate",
            "",
            f"CI gate status: {'PASS' if _gate_passed(summary) else 'WARN'}",
            "",
            "## Scenarios",
            "",
            "| Scenario | Feasible | Constraints | Faithfulness | Gap | NDCG@5 | Variants | On-time |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for result in results:
        lines.append(
            f"| {result.scenario_id} | {result.feasible} | {result.constraints_satisfied} | "
            f"{result.explanation_faithfulness} | "
            f"{_fmt(result.route_quality_gap)} | {_fmt(result.ndcg_at_5)} | "
            f"{result.route_variant_count} | {_fmt(result.on_time_prob)} |"
        )
    return "\n".join(lines) + "\n"


def _route_quality_gap(payload: dict[str, Any], scenario: dict[str, Any]) -> float | None:
    pool = payload.get("pool") or {}
    pois = [poi for category in pool.get("categories", []) for poi in category.get("pois", [])]
    if not pois:
        return None
    selected_ids = (
        (pool.get("default_selected_ids") or [])
        or [stop.get("poi_id") for stop in (payload.get("story_plan") or {}).get("stops", [])]
    )
    pois = _top_eval_pois(pois, selected_ids, limit=8)
    request = scenario["request"]
    time_window = request.get("time_window") or {"start": "13:00", "end": "21:00"}
    start_min = minutes_between("00:00", time_window["start"])
    end_min = minutes_between("00:00", time_window["end"])
    nodes = [
        OptwNode(
            poi_id=poi["id"],
            category=poi.get("category", ""),
            utility=float(poi.get("suitable_score") or 0) * 100,
            visit_min=55 if poi.get("category") == "restaurant" else 40,
            price=int(poi.get("price_per_person") or 0),
            open_min=start_min,
            close_min=end_min,
            queue_min=int(poi.get("estimated_queue_min") or 0),
        )
        for poi in pois
    ]
    travel = {
        (left.poi_id, right.poi_id): 10
        for left in nodes
        for right in nodes
        if left.poi_id != right.poi_id
    }
    max_stops = min(5, len(nodes))
    exact = solve_optw(
        nodes,
        travel,
        start_min=start_min,
        end_min=end_min,
        budget=request.get("budget_per_person"),
        must_visit=set(scenario.get("expected", {}).get("must_visit_ids", [])),
        required_categories=set(),
        required_category_groups=[],
        max_stops=max_stops,
        solver_mode="exact",
    )
    utility_by_id = {node.poi_id: node.utility for node in nodes}
    selected_utility = sum(utility_by_id.get(poi_id, 0.0) for poi_id in selected_ids[:max_stops])
    if exact.selected_utility <= 0:
        return None
    return round(max(0.0, (exact.selected_utility - selected_utility) / exact.selected_utility), 3)


def _route_ndcg_at_5(payload: dict[str, Any]) -> float | None:
    pool = payload.get("pool") or {}
    pois = [poi for category in pool.get("categories", []) for poi in category.get("pois", [])]
    if not pois:
        return None
    score_by_id = {poi["id"]: int(round(float(poi.get("suitable_score") or 0) * 5)) for poi in pois}
    selected_ids = list(pool.get("default_selected_ids") or [])
    selected_ids.extend(
        poi_id
        for poi_id, _ in sorted(score_by_id.items(), key=lambda item: item[1], reverse=True)
        if poi_id not in selected_ids
    )
    return ndcg_at_k([score_by_id[poi_id] for poi_id in selected_ids if poi_id in score_by_id], k=5)


def _top_eval_pois(pois: list[dict[str, Any]], selected_ids: list[str], *, limit: int) -> list[dict[str, Any]]:
    selected_set = set(selected_ids)
    by_id = {poi["id"]: poi for poi in pois}
    selected = [by_id[poi_id] for poi_id in selected_ids if poi_id in by_id]
    remaining = sorted(
        [poi for poi in pois if poi["id"] not in selected_set],
        key=lambda poi: float(poi.get("suitable_score") or 0),
        reverse=True,
    )
    return [*selected, *remaining[: max(0, limit - len(selected))]]


def _gate_passed(summary: dict[str, float]) -> bool:
    return (
        summary["feasible_rate"] >= 0.8
        and summary["constraint_satisfaction_rate"] >= 0.9
        and summary["explanation_faithfulness"] >= 0.9
        and summary["avg_route_quality_gap"] <= 0.5
    )


def _fmt(value: float | None) -> str:
    return "-" if value is None else str(value)


def _patch_local_route_client() -> None:
    class LocalRouteClient:
        def get_route(self, **kwargs: Any) -> AmapRouteResult:
            return AmapRouteResult(
                mode=AmapRouteMode.DRIVING,
                distance_m=1000,
                duration_s=600,
                steps=[
                    AmapRouteStep(
                        instruction="offline eval segment",
                        road_name="eval",
                        distance_m=1000,
                        duration_s=600,
                        polyline_coordinates=[],
                    )
                ],
                polyline_coordinates=[],
                raw_response={"offline_eval": True},
            )

        def close(self) -> None:
            return None

    routes_route.AmapRouteClient = LocalRouteClient


class _DictStop:
    def __init__(self, data: dict[str, Any]) -> None:
        self.poi_id = data.get("poi_id")
        self.why = data.get("why", "")


class _DictStory:
    def __init__(self, data: dict[str, Any]) -> None:
        self.stops = [_DictStop(item) for item in data.get("stops", [])]


if __name__ == "__main__":
    main()

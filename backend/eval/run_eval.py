from __future__ import annotations

import argparse
import json
from math import log
from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient

from app.api import routes_route
from app.main import app
from app.ml.ranker import ndcg_at_k
from app.repositories.poi_repo import get_poi_repository
from app.services.amap.schemas import AmapRouteMode, AmapRouteResult, AmapRouteStep
from app.solver.distance import haversine_meters
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
    selected_ids = _selected_ids(payload)
    selected_pois = repo.get_many(selected_ids)
    variant_overlap = _variant_jaccard_overlap(payload)
    category_entropy = _category_entropy([poi.category for poi in selected_pois])
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
        variant_jaccard_overlap=variant_overlap,
        category_entropy=category_entropy,
        business_area_spread=_business_area_spread(selected_pois),
        soft_constraint_tradeoff_score=_soft_constraint_tradeoff_score(payload, scenario, selected_pois),
        scenario_expectation_passed=_scenario_expectation_passed(
            payload,
            scenario,
            selected_pois,
            variant_overlap=variant_overlap,
            category_entropy=category_entropy,
        ),
    )


def _render_report(results: list[EvalResult]) -> str:
    summary = aggregate(results)
    lines = [
        "# AIroute 离线评估报告",
        "",
        "## 汇总指标",
        "",
        "| 指标 | Key | 数值 |",
        "| --- | --- | ---: |",
    ]
    lines.extend(f"| {_metric_label(key)} | {key} | {value} |" for key, value in summary.items())
    lines.extend(
        [
            "",
            "## 门禁结果",
            "",
            f"CI 门禁状态: {'通过' if _gate_passed(summary) else '警告'}",
            "",
            "## 场景明细",
            "",
            "| 场景说明 | ID | 可行 | 约束满足 | 解释忠实度 | 质量差距 | NDCG@5 | 方案数 | 准时概率 | 方案重叠度 | 品类熵 | 业务预期通过 |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for result in results:
        lines.append(
            f"| {_scenario_description(result.scenario_id)} | {result.scenario_id} | "
            f"{_fmt_bool(result.feasible)} | "
            f"{_fmt_bool(result.constraints_satisfied)} | "
            f"{result.explanation_faithfulness} | "
            f"{_fmt(result.route_quality_gap)} | {_fmt(result.ndcg_at_5)} | "
            f"{result.route_variant_count} | {_fmt(result.on_time_prob)} | "
            f"{_fmt(result.variant_jaccard_overlap)} | {_fmt(result.category_entropy)} | "
            f"{_fmt_bool(result.scenario_expectation_passed)} |"
        )
    return "\n".join(lines) + "\n"


def _metric_label(key: str) -> str:
    labels = {
        "scenario_count": "场景数量",
        "feasible_rate": "可行率",
        "constraint_satisfaction_rate": "约束满足率",
        "explanation_faithfulness": "解释忠实度",
        "avg_tool_count": "平均工具调用数",
        "avg_latency_ms": "平均耗时（毫秒）",
        "total_tokens": "总 Token 数",
        "avg_route_quality_gap": "平均路线质量差距",
        "avg_ndcg_at_5": "平均 NDCG@5",
        "avg_route_variant_count": "平均候选方案数",
        "avg_on_time_prob": "平均准时概率",
        "avg_variant_jaccard_overlap": "平均方案 Jaccard 重叠度",
        "avg_category_entropy": "平均品类熵",
        "avg_business_area_spread": "平均商圈分散度",
        "avg_soft_constraint_tradeoff_score": "平均软约束取舍分",
        "scenario_expectation_pass_rate": "场景业务预期通过率",
    }
    return labels.get(key, key)


def _scenario_description(scenario_id: str) -> str:
    descriptions = {
        "budget_tight": "低预算半日路线：80 元内、本地菜、避免高价点",
        "family_rainy": "雨天家庭室内路线：文化、咖啡、商场、节奏轻松",
        "food_interleave_guardrail": "餐饮穿插护栏：两餐之间加入文化或购物停留",
        "half_day_food": "半日本地美食：少排队、本地菜、顺路拍照",
        "hot_budget_indoor": "炎热低预算室内路线：轻餐、咖啡或商场、少通勤",
        "low_queue": "少排队效率路线：避开热门排队并包含午餐",
        "must_visit": "必去点路线：围绕城市博物馆补充餐饮和文化停留",
        "photo_cafe_culture": "拍照咖啡文化路线：咖啡、文化和轻松餐饮组合",
        "rainy_parent_child_short": "雨天亲子短路线：室内为主、含简餐、换乘短",
        "shopping_dinner_evening": "晚间购物晚餐路线：商场或文化开场，穿插不同餐饮",
    }
    return descriptions.get(scenario_id, f"自定义评估场景：{scenario_id}")


def _fmt_bool(value: bool) -> str:
    return "是" if value else "否"


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


def _selected_ids(payload: dict[str, Any]) -> list[str]:
    if payload.get("ordered_poi_ids"):
        return list(payload["ordered_poi_ids"])
    pool = payload.get("pool") or {}
    if pool.get("default_selected_ids"):
        return list(pool["default_selected_ids"])
    return [stop.get("poi_id") for stop in (payload.get("story_plan") or {}).get("stops", []) if stop.get("poi_id")]


def _variant_jaccard_overlap(payload: dict[str, Any]) -> float | None:
    routes = [variant.get("ordered_ids") or [] for variant in payload.get("route_variants") or []]
    routes = [route for route in routes if route]
    if len(routes) < 2:
        return None
    overlaps: list[float] = []
    for index, left in enumerate(routes):
        for right in routes[index + 1 :]:
            left_set = set(left)
            right_set = set(right)
            overlaps.append(len(left_set & right_set) / max(len(left_set | right_set), 1))
    return round(sum(overlaps) / max(len(overlaps), 1), 3)


def _category_entropy(categories: list[str]) -> float | None:
    categories = [category for category in categories if category]
    if not categories:
        return None
    counts = {category: categories.count(category) for category in set(categories)}
    entropy = -sum((count / len(categories)) * log(count / len(categories)) for count in counts.values())
    return round(entropy, 3)


def _business_area_spread(pois: list[Any]) -> float | None:
    areas = [getattr(poi, "business_area", None) or getattr(poi, "district", None) for poi in pois]
    areas = [area for area in areas if area]
    if not areas:
        return None
    return round(len(set(areas)) / len(areas), 3)


def _soft_constraint_tradeoff_score(
    payload: dict[str, Any],
    scenario: dict[str, Any],
    selected_pois: list[Any],
) -> float | None:
    if not selected_pois:
        return None
    request = scenario["request"]
    scores: list[float] = []
    budget = request.get("budget_per_person")
    if budget:
        total_cost = sum(int(getattr(poi, "price_per_person", 0) or 0) for poi in selected_pois)
        scores.append(1.0 if total_cost <= budget else max(0.0, 1.0 - ((total_cost - budget) / budget)))
    queue_total = sum(int((getattr(poi, "queue_estimate", {}) or {}).get("weekend_peak", 0) or 0) for poi in selected_pois)
    queue_threshold = 45 if "queue" in str(request.get("free_text", "")).lower() or "排队" in str(request.get("free_text", "")) else 60
    scores.append(max(0.0, min(1.0, 1.0 - (queue_total / max(len(selected_pois), 1)) / queue_threshold)))
    weather = request.get("weather_condition") or ""
    text = str(request.get("free_text") or "").lower()
    if weather in {"rainy", "hot", "cold"} or "rainy" in text or "雨" in text:
        indoor = {"restaurant", "cafe", "culture", "shopping", "entertainment"}
        scores.append(sum(poi.category in indoor for poi in selected_pois) / len(selected_pois))
    return round(sum(scores) / max(len(scores), 1), 3)


def _scenario_expectation_passed(
    payload: dict[str, Any],
    scenario: dict[str, Any],
    selected_pois: list[Any],
    *,
    variant_overlap: float | None,
    category_entropy: float | None,
) -> bool:
    expected = scenario.get("expected") or {}
    checks: list[bool] = []
    if "max_variant_jaccard_overlap" in expected and variant_overlap is not None:
        checks.append(variant_overlap <= float(expected["max_variant_jaccard_overlap"]))
    if "min_category_entropy" in expected and category_entropy is not None:
        checks.append(category_entropy >= float(expected["min_category_entropy"]))
    if "min_indoor_ratio" in expected and selected_pois:
        indoor = {"restaurant", "cafe", "culture", "shopping", "entertainment"}
        checks.append(sum(poi.category in indoor for poi in selected_pois) / len(selected_pois) >= float(expected["min_indoor_ratio"]))
    if "max_avg_queue_min" in expected and selected_pois:
        queue_total = sum(int((getattr(poi, "queue_estimate", {}) or {}).get("weekend_peak", 0) or 0) for poi in selected_pois)
        checks.append(queue_total / len(selected_pois) <= float(expected["max_avg_queue_min"]))
    if "max_budget_violation_ratio" in expected and selected_pois:
        budget = scenario["request"].get("budget_per_person") or 0
        total_cost = sum(int(getattr(poi, "price_per_person", 0) or 0) for poi in selected_pois)
        violation = max(0, total_cost - budget) / max(budget, 1)
        checks.append(violation <= float(expected["max_budget_violation_ratio"]))
    if "max_restaurant_count" in expected and selected_pois:
        checks.append(_restaurant_count(selected_pois) <= int(expected["max_restaurant_count"]))
    if "min_non_restaurant_count" in expected and selected_pois:
        checks.append(
            sum(getattr(poi, "category", None) != "restaurant" for poi in selected_pois)
            >= int(expected["min_non_restaurant_count"])
        )
    if expected.get("no_adjacent_restaurants") and selected_pois:
        categories = [getattr(poi, "category", None) for poi in selected_pois]
        checks.append(
            not any(left == right == "restaurant" for left, right in zip(categories, categories[1:]))
        )
    if expected.get("unique_restaurant_subcategories") and selected_pois:
        sub_categories = [
            str(getattr(poi, "sub_category", None) or getattr(poi, "category", None) or "")
            for poi in selected_pois
            if getattr(poi, "category", None) == "restaurant"
        ]
        checks.append(len(sub_categories) == len(set(sub_categories)))
    distances = _straight_segment_distances(selected_pois)
    if "max_straight_segment_m" in expected and distances:
        checks.append(max(distances) <= float(expected["max_straight_segment_m"]))
    if "max_straight_total_m" in expected and distances:
        checks.append(sum(distances) <= float(expected["max_straight_total_m"]))
    return all(checks) if checks else True


def _restaurant_count(selected_pois: list[Any]) -> int:
    return sum(getattr(poi, "category", None) == "restaurant" for poi in selected_pois)


def _straight_segment_distances(selected_pois: list[Any]) -> list[float]:
    distances: list[float] = []
    for left, right in zip(selected_pois, selected_pois[1:]):
        if not all(hasattr(item, attr) for item in (left, right) for attr in ("latitude", "longitude")):
            continue
        distances.append(haversine_meters(left, right))
    return distances


def _gate_passed(summary: dict[str, float]) -> bool:
    return (
        summary["feasible_rate"] >= 0.8
        and summary["constraint_satisfaction_rate"] >= 0.9
        and summary["explanation_faithfulness"] >= 0.9
        and summary["avg_route_quality_gap"] <= 0.5
        and summary["scenario_expectation_pass_rate"] >= 0.8
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

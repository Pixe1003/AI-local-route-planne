import json
import os
from pathlib import Path
from typing import Any

import pytest

from app.agent.conductor import Conductor
from app.agent.tools import get_tool_registry
from app.api import routes_route
from app.api.routes_agent import AgentRunRequest, build_initial_state
from app.llm.client import LlmClient
from app.repositories.poi_repo import get_poi_repository
from app.services.amap.schemas import AmapRouteMode, AmapRouteResult, AmapRouteStep


PROMPT_EVAL_PATH = Path(__file__).parent / "prompt_eval" / "story.eval.jsonl"
PASS_RATE_GATE = 0.85


@pytest.mark.skipif(
    not os.getenv("RUN_LLM_EVAL"),
    reason="LLM regression eval requires API key; set RUN_LLM_EVAL=1 to enable",
)
def test_story_prompt_regression_pass_rate(monkeypatch) -> None:
    _patch_route_client(monkeypatch)
    cases = [
        json.loads(line)
        for line in PROMPT_EVAL_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    repo = get_poi_repository()

    results = []
    for case in cases:
        state = _run_one_case(case)
        ok, detail = _evaluate(state, case, repo)
        results.append({"case": case["id"], "passed": ok, "detail": detail})

    output = Path("../data/eval/prompt_regression.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    passed = sum(1 for item in results if item["passed"])
    assert passed / len(results) >= PASS_RATE_GATE


def _run_one_case(case: dict[str, Any]):
    request = AgentRunRequest(
        user_id=f"prompt_eval_{case['id']}",
        free_text=case["input"]["query"],
        city=case["input"].get("city", "hefei"),
        date="2026-05-08",
        time_window={"start": "12:00", "end": "20:00"},
        budget_per_person=case["input"].get("budget_per_person", 180),
    )
    state = build_initial_state(request)
    return Conductor(get_tool_registry(), LlmClient()).run(state)


def _evaluate(state, case: dict[str, Any], repo) -> tuple[bool, dict[str, bool]]:
    story = state.memory.story_plan
    if story is None:
        return False, {"no_story_plan": False}
    expected = case["expected"]
    categories = {repo.get(stop.poi_id).category for stop in story.stops if _safe_get(repo, stop.poi_id)}
    checks = {
        "stops_in_range": expected.get("min_stops", 0)
        <= len(story.stops)
        <= expected.get("max_stops", 99),
        "evidence_grounded": all(stop.ugc_quote_ref and stop.ugc_quote for stop in story.stops),
    }
    if "must_include_categories" in expected:
        checks["categories_included"] = set(expected["must_include_categories"]) <= categories
    if "forbidden_categories" in expected:
        checks["no_forbidden"] = not (set(expected["forbidden_categories"]) & categories)
    if "theme_must_contain_any" in expected:
        checks["theme_match"] = any(
            term in (story.theme or "") for term in expected["theme_must_contain_any"]
        )
    return all(checks.values()), checks


def _safe_get(repo, poi_id: str) -> bool:
    try:
        repo.get(poi_id)
    except KeyError:
        return False
    return True


def _patch_route_client(monkeypatch) -> None:
    class FakeRouteClient:
        def get_route(self, **kwargs: Any) -> AmapRouteResult:
            return AmapRouteResult(
                mode=AmapRouteMode.DRIVING,
                distance_m=900,
                duration_s=480,
                steps=[
                    AmapRouteStep(
                        instruction="drive",
                        road_name="demo road",
                        distance_m=900,
                        duration_s=480,
                        polyline_coordinates=[[117.23, 31.82], [117.24, 31.83]],
                    )
                ],
                polyline_coordinates=[],
                raw_response={"status": "1"},
            )

        def close(self) -> None:
            return None

    monkeypatch.setattr(routes_route, "AmapRouteClient", FakeRouteClient, raising=False)

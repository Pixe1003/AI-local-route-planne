import json
from pathlib import Path
from typing import Any

from app.agent.conductor import Conductor
from app.agent.tools import get_tool_registry
from app.api import routes_route
from app.api.routes_agent import AgentRunRequest, build_initial_state
from app.llm.client import LlmClient
from app.repositories.poi_repo import get_poi_repository
from app.services.amap.schemas import AmapRouteMode, AmapRouteResult, AmapRouteStep


EVAL_CASES = [
    {
        "id": "case_quiet_friends_evening",
        "query": "晚上六点想和闺蜜聊聊，预算 150，少排队",
        "expected_terms": ["Route", "路线", "Taste"],
        "expected_categories": {"restaurant"},
    },
    {
        "id": "case_rainy_indoor",
        "query": "下雨天，找个室内不无聊的，吃顿好的",
        "expected_terms": ["Route", "路线", "Taste"],
        "expected_categories": {"restaurant"},
    },
    {
        "id": "case_local_lunch_photos",
        "query": "中午想吃合肥本地菜，顺便能拍点照",
        "expected_terms": ["Route", "路线", "Taste"],
        "expected_categories": {"restaurant"},
    },
    {
        "id": "case_hotpot_budget",
        "query": "想吃火锅，人均 180，别排太久",
        "expected_terms": ["Route", "路线", "Taste"],
        "expected_categories": {"restaurant"},
    },
    {
        "id": "case_cafe_chat",
        "query": "找个安静咖啡，再接一个晚饭",
        "expected_terms": ["Route", "路线", "Taste"],
        "expected_categories": {"restaurant"},
    },
    {
        "id": "case_family_easy",
        "query": "朋友小聚，路线轻松一点，别太贵",
        "expected_terms": ["Route", "路线", "Taste"],
        "expected_categories": {"restaurant"},
    },
    {
        "id": "case_photo_food",
        "query": "想边吃边拍照，下午到晚上",
        "expected_terms": ["Route", "路线", "Taste"],
        "expected_categories": {"restaurant"},
    },
    {
        "id": "case_local_specials",
        "query": "合肥特色小吃优先，交通别太绕",
        "expected_terms": ["Route", "路线", "Taste"],
        "expected_categories": {"restaurant"},
    },
]


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


def run_one(case: dict):
    request = AgentRunRequest(
        user_id=f"eval_{case['id']}",
        free_text=case["query"],
        city="hefei",
        date="2026-05-08",
        time_window={"start": "12:00", "end": "20:00"},
        budget_per_person=200,
    )
    state = build_initial_state(request)
    return Conductor(get_tool_registry(), LlmClient()).run(state)


def evaluate(state, case: dict) -> tuple[bool, dict[str, Any]]:
    story = state.memory.story_plan
    if story is None:
        return False, {"reason": "no_story_plan"}
    text = f"{story.theme} {story.narrative}"
    repo = get_poi_repository()
    stop_categories = {repo.get(stop.poi_id).category for stop in story.stops}
    detail = {
        "has_term": any(term in text for term in case["expected_terms"]),
        "categories_ok": case["expected_categories"] <= stop_categories,
        "evidence_grounded": all(stop.ugc_quote_ref and stop.ugc_quote for stop in story.stops),
        "validation_ok": bool(state.memory.validation and state.memory.validation.is_valid),
    }
    return all(detail.values()), detail


def test_agent_eval_pipeline_pass_rate(monkeypatch) -> None:
    _patch_route_client(monkeypatch)
    results = []
    passed = 0
    for case in EVAL_CASES:
        state = run_one(case)
        ok, detail = evaluate(state, case)
        results.append({"case": case["id"], "passed": ok, "detail": detail})
        if ok:
            passed += 1

    output = Path("../data/eval/last_run.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    assert passed / len(EVAL_CASES) >= 0.7

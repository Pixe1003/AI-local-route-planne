import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.agent.conductor import Conductor
from app.agent.tools import get_tool_registry
from app.api import routes_route
from app.api.routes_agent import AgentRunRequest, build_initial_state
from app.llm.client import LlmClient
from app.services.amap.schemas import AmapRouteMode, AmapRouteResult, AmapRouteStep


JUDGE_SYSTEM = """
You are a route-plan quality judge. Score the given user query and AIroute story plan
from 0 to 10 on exactly these dimensions:
- theme_coherence
- evidence_grounding
- pacing
- preference_fit
- narrative_quality

Return strict JSON with those five integer fields and overall_comment under 30 words.
"""


@pytest.mark.skipif(
    not os.getenv("RUN_LLM_JUDGE") or not os.getenv("JUDGE_LLM_API_KEY"),
    reason="LLM-as-judge eval requires RUN_LLM_JUDGE=1 and JUDGE_LLM_API_KEY",
)
def test_agent_output_quality_via_judge(monkeypatch) -> None:
    _patch_route_client(monkeypatch)
    queries = [
        "local food with less queue",
        "evening friends route budget 150",
        "rainy indoor food route",
    ]
    judge_scores = []
    for query in queries:
        state = _run_agent_with_query(query)
        story = state.memory.story_plan
        assert story is not None, f"Agent failed for query: {query}"
        result = _invoke_judge(
            JUDGE_SYSTEM,
            f"User query: {query}\n\nAgent story plan: {story.model_dump_json()}",
        )
        judge_scores.append({"query": query, "scores": result})

    output = Path("../data/eval/judge_scores.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(judge_scores, ensure_ascii=False, indent=2), encoding="utf-8")

    for entry in judge_scores:
        scores = entry["scores"]
        avg = sum(
            scores[key]
            for key in [
                "theme_coherence",
                "evidence_grounding",
                "pacing",
                "preference_fit",
                "narrative_quality",
            ]
        ) / 5
        assert avg >= 7, f"Query {entry['query']!r} got avg {avg:.1f} < 7"


def _run_agent_with_query(query: str):
    request = AgentRunRequest(
        user_id=f"judge_{abs(hash(query))}",
        free_text=query,
        city="hefei",
        date="2026-05-08",
        time_window={"start": "12:00", "end": "20:00"},
        budget_per_person=180,
    )
    state = build_initial_state(request)
    return Conductor(get_tool_registry(), LlmClient()).run(state)


def _invoke_judge(system: str, user_input: str) -> dict[str, Any]:
    response = httpx.post(
        "https://api.deepseek.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {os.environ['JUDGE_LLM_API_KEY']}",
            "Content-Type": "application/json",
        },
        json={
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_input},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        },
        timeout=30,
    )
    response.raise_for_status()
    return json.loads(response.json()["choices"][0]["message"]["content"])


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

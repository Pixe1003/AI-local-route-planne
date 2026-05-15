import json
import re
from datetime import datetime, timezone
from pathlib import Path

from app.agent.state import AgentGoal, AgentState
from app.agent.tools import _compose_story
from app.schemas.onboarding import UserNeedProfile
from app.schemas.plan import HardConstraints, PlanContext, SoftPreferences, StructuredIntent
from app.schemas.pool import PoiInPool, PoolCategory, PoolMeta, PoolResponse, TimeWindow


def _state_with_pool() -> AgentState:
    context = PlanContext(
        city="hefei",
        date="2026-05-08",
        time_window=TimeWindow(start="12:00", end="20:00"),
        party="friends",
        budget_per_person=180,
    )
    state = AgentState(
        goal=AgentGoal(raw_query="local food", user_id="quality_user", locale_city="hefei"),
        profile=UserNeedProfile.from_plan_context(context, raw_query="local food"),
        context=context,
    )
    state.memory.intent = StructuredIntent(
        hard_constraints=HardConstraints(
            start_time="12:00",
            end_time="20:00",
            budget_total=180,
            must_include_meal=True,
        ),
        soft_preferences=SoftPreferences(),
        must_visit_pois=[],
        avoid_pois=[],
    )
    state.memory.pool = PoolResponse(
        pool_id="quality_pool",
        default_selected_ids=["hf_poi_061581", "hf_poi_000086", "hf_poi_083759"],
        categories=[
            PoolCategory(
                name="food",
                description="food",
                pois=[
                    PoiInPool(
                        id="hf_poi_061581",
                        name="Local Restaurant",
                        category="restaurant",
                        rating=4.6,
                        price_per_person=70,
                        cover_image=None,
                        distance_meters=None,
                        why_recommend="food",
                        highlight_quote="local food quote",
                        keywords=[],
                        estimated_queue_min=20,
                        suitable_score=0.9,
                    )
                ],
            ),
            PoolCategory(
                name="culture",
                description="culture",
                pois=[
                    PoiInPool(
                        id="hf_poi_000086",
                        name="Culture Stop",
                        category="culture",
                        rating=4.4,
                        price_per_person=40,
                        cover_image=None,
                        distance_meters=None,
                        why_recommend="culture",
                        highlight_quote="culture quote",
                        keywords=[],
                        estimated_queue_min=10,
                        suitable_score=0.8,
                    )
                ],
            ),
            PoolCategory(
                name="cafe",
                description="cafe",
                pois=[
                    PoiInPool(
                        id="hf_poi_083759",
                        name="Cafe Stop",
                        category="cafe",
                        rating=4.3,
                        price_per_person=35,
                        cover_image=None,
                        distance_meters=None,
                        why_recommend="cafe",
                        highlight_quote="cafe quote",
                        keywords=[],
                        estimated_queue_min=5,
                        suitable_score=0.7,
                    )
                ],
            ),
        ],
        meta=PoolMeta(
            total_count=3,
            generated_at=datetime.now(timezone.utc),
            user_persona_summary="quality",
        ),
    )
    return state


def test_prompt_loader_returns_versioned_prompt() -> None:
    from app.agent.prompts import get_prompt_version, load_prompt

    content, version = load_prompt("story")

    assert version == get_prompt_version("story")
    assert re.fullmatch(r"v\d+\.\d+\.\d+", version)
    assert "Use only supplied POI ids" in content


def test_compose_story_result_includes_prompt_version_ref() -> None:
    from app.agent.prompts import get_prompt_version

    result = _compose_story(_state_with_pool(), {})

    assert result.observation_payload_ref == f"prompt:story@{get_prompt_version('story')}"


def test_prompt_eval_fixture_has_required_cases() -> None:
    path = Path(__file__).parent / "prompt_eval" / "story.eval.jsonl"
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    assert len(cases) >= 12
    assert {case["id"] for case in cases}
    assert all("input" in case and "expected" in case for case in cases)

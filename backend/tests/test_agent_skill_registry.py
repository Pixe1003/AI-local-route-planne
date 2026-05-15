from types import SimpleNamespace

from app.llm.client import LlmClient
from app.services.agent_skill_registry import AgentSkillRegistry
from app.services.intent_service import IntentService
from app.services.onboarding_service import OnboardingService
from app.services.plan_service import PlanService
from app.services.pool_service import PoolService
from app.services.route_replanner import RouteReplanner
from app.services.trip_service import TripService


def test_agent_skill_registry_loads_project_skill_by_agent_name():
    registry = AgentSkillRegistry()

    skill = registry.get_skill("need_profile")

    assert skill is not None
    assert skill.name == "need_profile"
    assert "Need Profile Agent" in skill.content
    assert "UserNeedProfile" in skill.content


def test_agent_skill_registry_builds_system_prompt_with_skill_content():
    registry = AgentSkillRegistry()

    prompt = registry.build_system_prompt(
        "route_planning",
        "你是本地路线规划系统的需求理解模块。只输出 JSON。",
    )

    assert "你是本地路线规划系统的需求理解模块" in prompt
    assert "<agent_skill name=\"route_planning\">" in prompt
    assert "Route Planning Agent" in prompt
    assert "Validate before presenting" in prompt


def test_llm_client_injects_agent_skill_into_system_message(monkeypatch):
    captured = {}

    def fake_settings():
        return SimpleNamespace(
            llm_api_key="test-key",
            llm_base_url="https://api.mimo-v2.com/v1",
            llm_auth_header="authorization",
            llm_model="mimo-v2-pro",
            llm_timeout_seconds=12,
        )

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "{\"ok\": true}"}}]}

    def fake_post(url, *, headers, json, timeout):
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr("app.llm.client.get_settings", fake_settings)
    monkeypatch.setattr("app.llm.client.httpx.post", fake_post)

    result = LlmClient().complete_json(
        "解析需求",
        {"fallback": True},
        agent_name="need_profile",
    )

    system_content = captured["json"]["messages"][0]["content"]
    assert result == {"ok": True}
    assert "<agent_skill name=\"need_profile\">" in system_content
    assert "Need Profile Agent" in system_content


def test_agent_services_load_their_corresponding_skills_by_name():
    assert OnboardingService().agent_skill.name == "need_profile"
    assert IntentService().agent_skill.name == "route_planning"
    assert PoolService().agent_skill.name == "recommend"
    assert PlanService().agent_skill.name == "route_planning"
    assert RouteReplanner().agent_skill.name == "replan"
    assert TripService().agent_skill.name == "trip_manager"

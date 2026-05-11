from types import SimpleNamespace

from app.llm.client import LlmClient
from app.schemas.onboarding import OnboardingProfileRequest
from app.schemas.plan import PlanContext
from app.schemas.pool import TimeWindow
from app.services.intent_service import IntentService
from app.services.onboarding_service import OnboardingService


def test_llm_client_posts_mimo_openai_compatible_request(monkeypatch):
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
            return {
                "choices": [
                    {
                        "message": {
                            "content": "```json\n{\"party_type\":\"couple\",\"route_style\":[\"少排队\"]}\n```"
                        }
                    }
                ]
            }

    def fake_post(url, *, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.llm.client.get_settings", fake_settings)
    monkeypatch.setattr("app.llm.client.httpx.post", fake_post)

    result = LlmClient().complete_json("解析需求", {"fallback": True})

    assert result["party_type"] == "couple"
    assert captured["url"] == "https://api.mimo-v2.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["json"]["model"] == "mimo-v2-pro"
    assert captured["json"]["messages"][0]["role"] == "system"
    assert captured["json"]["stop"] is None
    assert captured["json"]["frequency_penalty"] == 0
    assert captured["json"]["presence_penalty"] == 0
    assert captured["timeout"] == 12


def test_llm_client_posts_longcat_openai_compatible_request(monkeypatch):
    captured = {}

    def fake_settings():
        return SimpleNamespace(
            llm_provider="longcat",
            llm_api_key="test-longcat-key",
            llm_base_url="",
            llm_auth_header="authorization",
            llm_model="LongCat-Flash-Chat",
            llm_timeout_seconds=30,
        )

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "{\"ok\": true}"}}]}

    def fake_post(url, *, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.llm.client.get_settings", fake_settings)
    monkeypatch.setattr("app.llm.client.httpx.post", fake_post)

    result = LlmClient().complete_json("解析需求", {"fallback": True})

    assert result == {"ok": True}
    assert captured["url"] == "https://api.longcat.chat/openai/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-longcat-key"
    assert captured["json"]["model"] == "LongCat-Flash-Chat"
    assert captured["json"]["max_tokens"] == 1024
    assert "max_completion_tokens" not in captured["json"]
    assert captured["timeout"] == 30


def test_onboarding_profile_uses_llm_profile_when_available(monkeypatch):
    def fake_complete_json(self, prompt, fallback, *, agent_name=None, system_prompt=None):
        assert "UserNeedProfile" in prompt
        assert agent_name == "need_profile"
        return {
            "destination": {"city": "shanghai", "start_location": "静安寺"},
            "time": {"start_time": "15:00", "end_time": "19:00", "time_budget_minutes": 240},
            "activity_preferences": ["展览"],
            "food_preferences": ["本地菜"],
            "party_type": "friends",
            "budget": {"budget_per_person": 120, "strict": False},
            "route_style": ["少排队"],
            "avoid": ["长时间排队"],
        }

    monkeypatch.setattr("app.services.onboarding_service.LlmClient.complete_json", fake_complete_json)

    response = OnboardingService().build_profile(
        OnboardingProfileRequest(query="帮我安排一个路线", answers={})
    )

    assert response.profile.destination.start_location == "静安寺"
    assert response.profile.time.start_time == "15:00"
    assert response.profile.party_type == "friends"
    assert response.profile.budget.budget_per_person == 120
    assert response.profile.completeness_score >= 0.8


def test_intent_uses_llm_soft_preferences_without_overriding_hard_constraints(monkeypatch):
    def fake_complete_json(self, prompt, fallback, *, agent_name=None, system_prompt=None):
        assert "StructuredIntent" in prompt
        assert agent_name == "route_planning"
        return {
            "hard_constraints": {
                "start_time": "09:00",
                "end_time": "23:00",
                "budget_total": 9999,
                "must_include_meal": False,
            },
            "soft_preferences": {
                "pace": "relaxed",
                "avoid_queue": True,
                "weather_sensitive": True,
                "photography_priority": True,
                "food_diversity": True,
                "custom_notes": ["模型识别：雨天、少排队、拍照"],
            },
            "must_visit_pois": ["llm_should_not_override"],
            "avoid_pois": ["sh_poi_099"],
        }

    monkeypatch.setattr("app.services.intent_service.LlmClient.complete_json", fake_complete_json)

    context = PlanContext(
        city="shanghai",
        date="2026-05-02",
        time_window=TimeWindow(start="14:00", end="20:00"),
        party="couple",
        budget_per_person=200,
    )
    intent = IntentService().parse_intent(
        "mock_user", ["sh_poi_003"], "想找室内舒服一点的路线", context
    )

    assert intent.hard_constraints.start_time == "14:00"
    assert intent.hard_constraints.end_time == "20:00"
    assert intent.hard_constraints.budget_total == 400
    assert intent.must_visit_pois == ["sh_poi_003"]
    assert intent.soft_preferences.avoid_queue is True
    assert intent.soft_preferences.weather_sensitive is True
    assert intent.avoid_pois == ["sh_poi_099"]

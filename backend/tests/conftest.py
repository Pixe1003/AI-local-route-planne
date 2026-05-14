import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def isolate_llm_settings(monkeypatch):
    monkeypatch.setenv("AGENT_TOOL_CALLING_ENABLED", "false")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("AMAP_WEB_SERVICE_KEY", "")
    monkeypatch.setenv("AMAP_KEY", "")
    get_settings.cache_clear()
    get_settings()
    yield
    get_settings.cache_clear()

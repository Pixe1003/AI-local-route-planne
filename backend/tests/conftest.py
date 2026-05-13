import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def isolate_llm_settings(monkeypatch):
    monkeypatch.setenv("AGENT_TOOL_CALLING_ENABLED", "false")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def isolate_llm_settings(monkeypatch):
    monkeypatch.setenv("LOCAL_ROUTE_DISABLE_ENV_FILE", "1")
    monkeypatch.setenv("AGENT_TOOL_CALLING_ENABLED", "false")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("AMAP_WEB_SERVICE_KEY", "")
    monkeypatch.setenv("AMAP_KEY", "")
    monkeypatch.setenv("UGC_SEMANTIC_SEARCH_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def isolate_segment_route_cache():
    from app.api import routes_route

    routes_route._SEGMENT_ROUTE_CACHE.clear()
    yield
    routes_route._SEGMENT_ROUTE_CACHE.clear()


@pytest.fixture(autouse=True)
def isolate_cache_state(tmp_path, monkeypatch):
    from app.llm import cache as llm_cache
    from app.repositories import embedding_cache
    from app.services.amap import cache as amap_cache

    monkeypatch.setattr(amap_cache, "DB_PATH", tmp_path / "amap_cache.sqlite", raising=False)
    llm_cache.clear()
    embedding_cache.clear()
    yield
    llm_cache.clear()
    embedding_cache.clear()


@pytest.fixture(autouse=True)
def isolate_agent_memory_store(tmp_path, monkeypatch):
    from app.agent import store, user_memory

    monkeypatch.setattr(store, "DB_PATH", tmp_path / "agent_sessions.sqlite", raising=False)
    monkeypatch.setattr(store, "_persist_session_vector", lambda state: None, raising=False)
    user_memory._CACHE.clear()
    yield
    user_memory._CACHE.clear()

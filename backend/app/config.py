from functools import lru_cache
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    app_name: str = "local-route-agent"
    app_port: int = 8000
    frontend_port: int = 5173
    default_city: str = "hefei"
    llm_provider: str = "longcat"
    llm_api_key: str = ""
    llm_model: str = "longcat-max"
    llm_base_url: str = "https://api.longcat.ai/v1"
    llm_auth_header: str = ""
    llm_timeout_seconds: int = 30
    database_url: str = "postgresql://local_route:local_route@localhost:5432/local_route"
    vector_db_path: str = "./data/chroma"
    rag_enabled: bool = True
    faiss_index_path: str = "./data/faiss"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    ugc_reviews_path: str = "./data/processed/ugc_hefei.jsonl"
    amap_key: str = ""
    amap_web_service_key: str = ""
    amap_route_base_url: str = "https://restapi.amap.com"
    amap_route_timeout_seconds: float = 15.0
    agent_tool_calling_enabled: bool = True
    agent_fast_decision_enabled: bool = True
    prefer_tool_recall_in_trace: bool = False
    log_level: str = "INFO"
    ugc_semantic_search_enabled: bool = True
    otel_service_name: str = "airoute-agent"
    otel_exporter_otlp_endpoint: str = ""
    redis_url: str = ""
    route_solver: str = "optw"
    ranker_enabled: bool = True
    ranker_model_path: str = "data/models/ranker.txt"
    startup_warmup_enabled: bool = True
    startup_warmup_query: str = "warmup"
    semantic_retrieval_timeout_ms: int = 1200
    budget_first_semantic_timeout_ms: int = 600
    budget_first_threshold: int = 100
    semantic_timeout_cooldown_seconds: int = 60

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    if os.getenv("LOCAL_ROUTE_DISABLE_ENV_FILE") == "1":
        return Settings(_env_file=None)  # type: ignore[call-arg]
    return Settings()

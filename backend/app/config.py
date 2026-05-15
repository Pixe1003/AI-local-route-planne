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
    ugc_reviews_path: str = "./data/processed/ugc_hefei.jsonl"
    amap_key: str = ""
    amap_web_service_key: str = ""
    amap_route_base_url: str = "https://restapi.amap.com"
    amap_route_timeout_seconds: float = 15.0
    agent_tool_calling_enabled: bool = True

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    if os.getenv("LOCAL_ROUTE_DISABLE_ENV_FILE") == "1":
        return Settings(_env_file=None)
    return Settings()

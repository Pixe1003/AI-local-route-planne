from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "local-route-agent"
    app_port: int = 8000
    frontend_port: int = 5173
    default_city: str = "hefei"
    llm_provider: str = "deepseek"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_base_url: str = ""
    llm_auth_header: str = ""
    llm_timeout_seconds: int = 20
    database_url: str = "postgresql://local_route:local_route@localhost:5432/local_route"
    poi_sqlite_path: str = "./data/processed/hefei_pois.sqlite"
    rag_enabled: bool = True
    vector_db_path: str = "./data/chroma"
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_timeout_seconds: int = 30
    amap_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

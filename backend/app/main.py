from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from pathlib import Path

from app.api import (
    routes_chat,
    routes_agent,
    routes_meta,
    routes_onboarding,
    routes_plan,
    routes_pool,
    routes_preferences,
    routes_route,
    routes_trips,
    routes_ugc,
)
from app.config import get_settings
from app.observability.logging import configure_logging
from app.observability.tracing import configure_otel, instrument_fastapi_app
from app.repositories.faiss_index import FaissVectorIndex

settings = get_settings()
configure_logging(level=settings.log_level)
configure_otel(
    service_name=settings.otel_service_name,
    endpoint=settings.otel_exporter_otlp_endpoint or None,
)

app = FastAPI(title="AI 本地路线智能规划系统", version="0.1.0")
instrument_fastapi_app(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_pool.router, prefix="/api")
app.include_router(routes_agent.router, prefix="/api")
app.include_router(routes_plan.router, prefix="/api")
app.include_router(routes_chat.router, prefix="/api")
app.include_router(routes_meta.router, prefix="/api")
app.include_router(routes_onboarding.router, prefix="/api")
app.include_router(routes_trips.router, prefix="/api")
app.include_router(routes_ugc.router, prefix="/api")
app.include_router(routes_preferences.router, prefix="/api")
app.include_router(routes_route.router, prefix="/api")

Instrumentator(should_group_status_codes=False).instrument(app).expose(app, endpoint="/metrics")


@app.get("/health")
def health() -> dict:
    faiss_index = FaissVectorIndex(settings.faiss_index_path)
    project_root = Path(__file__).resolve().parents[2]
    memory_db = project_root / "data" / "processed" / "agent_sessions.sqlite"
    faiss_exists = faiss_index.exists()
    faiss_count = faiss_index.count()
    rag_status = "disabled"
    if settings.rag_enabled:
        rag_status = "ready" if faiss_exists and faiss_count > 0 else "degraded"
    amap_configured = bool(settings.amap_web_service_key or settings.amap_key)
    memory_exists = memory_db.exists()
    return {
        "status": "ok",
        "service": settings.app_name,
        "rag": {
            "enabled": settings.rag_enabled,
            "engine": "faiss",
            "status": rag_status,
        },
        "faiss": {
            "enabled": settings.rag_enabled,
            "index_path": str(faiss_index.index_path),
            "index_exists": faiss_exists,
            "document_count": faiss_count,
            "status": "ready" if faiss_exists and faiss_count > 0 else "missing_index",
        },
        "amap": {
            "configured": amap_configured,
            "base_url": settings.amap_route_base_url,
            "status": "ready" if amap_configured else "degraded",
        },
        "memory": {
            "enabled": True,
            "store_exists": memory_exists,
            "status": "ready" if memory_exists else "degraded",
        },
        "cache": {
            "status": "ready",
            "embedding": "memory_lru",
            "llm": "memory_ttl",
            "amap": "sqlite",
        },
    }

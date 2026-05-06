from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    routes_chat,
    routes_meta,
    routes_onboarding,
    routes_plan,
    routes_pool,
    routes_replan,
    routes_trips,
)
from app.config import get_settings

settings = get_settings()

app = FastAPI(title="AI 本地路线智能规划系统", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_pool.router, prefix="/api")
app.include_router(routes_plan.router, prefix="/api")
app.include_router(routes_chat.router, prefix="/api")
app.include_router(routes_meta.router, prefix="/api")
app.include_router(routes_onboarding.router, prefix="/api")
app.include_router(routes_replan.router, prefix="/api")
app.include_router(routes_trips.router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.route import router as route_router


app = FastAPI(title="Amap POI Route Planning Demo")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(route_router)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}

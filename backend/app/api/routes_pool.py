from fastapi import APIRouter

from app.schemas.pool import PoolRequest, PoolResponse
from app.services.orchestrator import AgentOrchestrator

router = APIRouter(prefix="/pool", tags=["pool"])


@router.post("/generate", response_model=PoolResponse)
def generate_pool(request: PoolRequest) -> PoolResponse:
    return AgentOrchestrator().generate_pool(request)

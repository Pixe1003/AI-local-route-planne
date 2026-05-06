from fastapi import APIRouter

from app.schemas.plan import PlanRequest, PlanResponse
from app.services.orchestrator import AgentOrchestrator

router = APIRouter(prefix="/plan", tags=["plan"])


@router.post("/generate", response_model=PlanResponse)
def generate_plan(request: PlanRequest) -> PlanResponse:
    return AgentOrchestrator().generate_plans(request)

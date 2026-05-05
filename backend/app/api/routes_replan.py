from fastapi import APIRouter
from pydantic import BaseModel

from app.services.route_replanner import ReplanEvent, ReplanResponse, RouteReplanner
from app.services.state import PLAN_REGISTRY

router = APIRouter(tags=["replan"])


class ReplanRouteRequest(BaseModel):
    plan_id: str
    event: ReplanEvent


@router.post("/replan-route", response_model=ReplanResponse)
def replan_route(request: ReplanRouteRequest) -> ReplanResponse:
    plan = PLAN_REGISTRY[request.plan_id]
    response = RouteReplanner().replan(plan, request.event)
    PLAN_REGISTRY[response.plan.plan_id] = response.plan
    return response

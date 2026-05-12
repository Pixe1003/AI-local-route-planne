from __future__ import annotations
from app.schemas.chat import ChatResponse, ChatTurn
from app.schemas.plan import PlanRequest, PlanResponse
from app.schemas.pool import PoolRequest, PoolResponse
from app.schemas.trip import SaveRouteVersionRequest, TripRecord, TripSummary
from app.services.chat_service import ChatService
from app.services.plan_service import PlanService
from app.services.pool_service import PoolService
from app.services.trip_service import TripService


class AgentOrchestrator:
    def generate_pool(self, request: PoolRequest) -> PoolResponse:
        return PoolService().generate_pool(request)

    def generate_plans(self, request: PlanRequest) -> PlanResponse:
        return PlanService().generate_plans(request)

    def adjust_plan(
        self,
        plan_id: str,
        user_message: str,
        chat_history: list[ChatTurn],
        action_type: str | None = None,
        target_stop_index: int | None = None,
        replacement_poi_id: str | None = None,
    ) -> ChatResponse:
        return ChatService().adjust_plan(
            plan_id,
            user_message,
            chat_history,
            action_type,
            target_stop_index,
            replacement_poi_id,
        )

    def list_trips(self, user_id: str) -> list[TripSummary]:
        return TripService().list_trips(user_id)

    def get_trip(self, trip_id: str) -> TripRecord | None:
        return TripService().get_trip(trip_id)

    def save_route_version(self, request: SaveRouteVersionRequest) -> TripRecord:
        return TripService().save_route_version(request)


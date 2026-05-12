from pydantic import BaseModel, Field
from fastapi import APIRouter

from app.schemas.chat import ChatResponse, ChatTurn
from app.schemas.pool import TimeWindow
from app.schemas.preferences import PreferenceSnapshot
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatAdjustRequest(BaseModel):
    plan_id: str | None = None
    pool_id: str | None = None
    current_poi_ids: list[str] = Field(default_factory=list)
    user_message: str
    chat_history: list[ChatTurn] = Field(default_factory=list)
    action_type: str | None = None
    target_stop_index: int | None = None
    replacement_poi_id: str | None = None
    city: str = "hefei"
    date: str = "2026-05-02"
    time_window: TimeWindow | None = None
    free_text: str | None = None
    preference_snapshot: PreferenceSnapshot | None = None


@router.post("/adjust", response_model=ChatResponse)
def adjust_plan(request: ChatAdjustRequest) -> ChatResponse:
    if request.plan_id is None:
        return ChatService().adjust_recommendations(
            pool_id=request.pool_id,
            current_poi_ids=request.current_poi_ids,
            user_message=request.user_message,
        )
    return ChatService().adjust_plan(
        request.plan_id,
        request.user_message,
        request.chat_history,
        request.action_type,
        request.target_stop_index,
        request.replacement_poi_id,
    )

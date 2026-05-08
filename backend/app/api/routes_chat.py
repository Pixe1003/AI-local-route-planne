from pydantic import BaseModel, Field
from fastapi import APIRouter

from app.schemas.chat import ChatResponse, ChatTurn
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatAdjustRequest(BaseModel):
    plan_id: str
    user_message: str
    chat_history: list[ChatTurn] = Field(default_factory=list)
    action_type: str | None = None
    target_stop_index: int | None = None
    replacement_poi_id: str | None = None


@router.post("/adjust", response_model=ChatResponse)
def adjust_plan(request: ChatAdjustRequest) -> ChatResponse:
    return ChatService().adjust_plan(
        request.plan_id,
        request.user_message,
        request.chat_history,
        request.action_type,
        request.target_stop_index,
        request.replacement_poi_id,
    )

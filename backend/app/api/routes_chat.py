from fastapi import APIRouter

from app.schemas.chat import ChatResponse, ChatTurn
from app.services.chat_service import ChatService
from pydantic import BaseModel

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatAdjustRequest(BaseModel):
    plan_id: str
    user_message: str
    chat_history: list[ChatTurn] = []


@router.post("/adjust", response_model=ChatResponse)
def adjust_plan(request: ChatAdjustRequest) -> ChatResponse:
    return ChatService().adjust_plan(
        request.plan_id,
        request.user_message,
        request.chat_history,
    )

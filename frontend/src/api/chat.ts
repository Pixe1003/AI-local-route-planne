import { apiClient } from "./client"
import type { ChatResponse, ChatTurn } from "../types/chat"

export async function adjustPlan(payload: {
  plan_id: string
  user_message: string
  chat_history: ChatTurn[]
}): Promise<ChatResponse> {
  return apiClient.post<ChatResponse, ChatResponse>("/chat/adjust", payload)
}

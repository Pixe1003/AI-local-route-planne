import { apiClient } from "./client"
import type { ChatAdjustRequest, ChatResponse } from "../types/chat"

export async function adjustPlan(payload: ChatAdjustRequest): Promise<ChatResponse> {
  return apiClient.post<ChatResponse, ChatResponse>("/chat/adjust", payload)
}

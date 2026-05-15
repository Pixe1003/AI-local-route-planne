import { apiClient } from "./client"
import type { AgentAdjustRequest, AgentRunRequest, AgentRunResponse } from "../types/agent"

export async function runAgentRoute(request: AgentRunRequest): Promise<AgentRunResponse> {
  return apiClient.post<AgentRunResponse, AgentRunResponse>("/agent/run", request)
}

export async function adjustAgentRoute(request: AgentAdjustRequest): Promise<AgentRunResponse> {
  return apiClient.post<AgentRunResponse, AgentRunResponse>("/agent/adjust", request)
}

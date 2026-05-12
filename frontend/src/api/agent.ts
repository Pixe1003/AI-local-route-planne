import { apiClient } from "./client"
import type { AgentRunRequest, AgentRunResponse } from "../types/agent"

export async function runAgentRoute(request: AgentRunRequest): Promise<AgentRunResponse> {
  return apiClient.post<AgentRunResponse, AgentRunResponse>("/agent/run", request)
}


import { apiClient } from "./client"
import type { AgentAdjustRequest, AgentRunRequest, AgentRunResponse } from "../types/agent"
import type { UserFacts } from "../types/userMemory"

export async function runAgentRoute(request: AgentRunRequest): Promise<AgentRunResponse> {
  return apiClient.post<AgentRunResponse, AgentRunResponse>("/agent/run", request)
}

export async function adjustAgentRoute(request: AgentAdjustRequest): Promise<AgentRunResponse> {
  return apiClient.post<AgentRunResponse, AgentRunResponse>("/agent/adjust", request)
}

export async function fetchUserFacts(userId: string, forceRefresh?: boolean): Promise<UserFacts> {
  const query = forceRefresh ? "?force_refresh=true" : ""
  return apiClient.get<UserFacts, UserFacts>(`/agent/user/${encodeURIComponent(userId)}/facts${query}`)
}

export function agentTraceStreamUrl(sessionId: string): string {
  const base = import.meta.env.VITE_API_BASE_URL || "/api"
  return `${base.replace(/\/$/, "")}/agent/stream/${sessionId}`
}

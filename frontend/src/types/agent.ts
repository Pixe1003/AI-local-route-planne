import type { PoolResponse, TimeWindow } from "./pool"
import type { PreferenceSnapshot } from "./preferences"
import type { RouteChainResponse } from "./route"

export interface AgentRunRequest {
  user_id: string
  free_text: string
  city: string
  time_window: TimeWindow
  date: string
  budget_per_person?: number
  preference_snapshot?: PreferenceSnapshot
  session_id?: string
  parent_session_id?: string
}

export interface AgentToolCall {
  tool_name: string
  args: Record<string, unknown>
  observation_summary?: string | null
  error?: string | null
  latency_ms: number
}

export interface AgentRunResponse {
  session_id: string
  trace_id: string
  phase: string
  ordered_poi_ids: string[]
  pool?: PoolResponse | null
  route_chain?: RouteChainResponse | null
  steps: AgentToolCall[]
}


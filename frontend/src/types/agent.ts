import type { PoolResponse, TimeWindow } from "./pool"
import type { PreferenceSnapshot } from "./preferences"
import type { RouteChainResponse } from "./route"
import type { StoryPlan } from "./story"
import type { UserNeedProfile } from "./onboarding"

export interface AgentCritique {
  theme_coherence: number
  evidence_strength: number
  pacing: number
  preference_fit: number
  narrative: number
  should_stop: boolean
  hint?: string | null
  issues: string[]
}

export interface AgentRunRequest {
  user_id: string
  free_text: string
  city: string
  time_window?: TimeWindow | null
  date: string
  budget_per_person?: number
  need_profile?: UserNeedProfile
  origin_latitude?: number
  origin_longitude?: number
  radius_meters?: number
  preference_snapshot?: PreferenceSnapshot
  session_id?: string
  parent_session_id?: string
}

export interface AgentAdjustRequest {
  parent_session_id: string
  user_message: string
  session_id?: string
}

export interface AgentToolCall {
  tool_name: string
  args: Record<string, unknown>
  observation_summary?: string | null
  error?: string | null
  latency_ms: number
}

export interface RouteOptimizationSummary {
  solver: string
  objective_value: number
  selected_utility: number
  constraint_violations: string[]
  optimality_gap: number | null
  fallback_used: boolean
}

export interface RouteVariantMetrics {
  interest: number
  time: number
  cost: number
  queue: number
}

export interface RouteVariant {
  label: string
  ordered_ids: string[]
  solver: string
  interest: number
  time_min: number
  cost: number
  queue_min: number
  metrics: RouteVariantMetrics
  objective_value: number
  non_dominated: boolean
  dominated_by?: string[]
}

export interface RobustnessSummary {
  on_time_prob: number
  expected_overflow_min: number
  p90_total_min: number
  samples: number
}

export interface AgentRunResponse {
  session_id: string
  trace_id: string
  phase: string
  ordered_poi_ids: string[]
  pool?: PoolResponse | null
  route_chain?: RouteChainResponse | null
  story_plan?: StoryPlan | null
  validation?: { is_valid: boolean; issues: unknown[]; repaired_count: number } | null
  critique?: AgentCritique | null
  steps: AgentToolCall[]
  route_optimization?: RouteOptimizationSummary | null
  route_variants?: RouteVariant[]
  robustness?: RobustnessSummary | null
}

import type { TimeWindow } from "./pool"
import type { UserNeedProfile } from "./onboarding"
import type { PreferenceSnapshot } from "./preferences"

export interface PlanContext {
  city: string
  date: string
  time_window: TimeWindow
  party?: string
  budget_per_person?: number
}

export interface PlanRequest {
  pool_id: string
  selected_poi_ids: string[]
  free_text?: string
  context?: PlanContext
  need_profile?: UserNeedProfile
  preference_snapshot?: PreferenceSnapshot
}

export interface Transport {
  mode: string
  duration_min: number
  distance_meters: number
}

export interface UgcSnippet {
  quote: string
  source: string
  date?: string | null
}

export interface RefinedStop {
  poi_id: string
  poi_name: string
  arrival_time: string
  departure_time: string
  why_this_one: string
  ugc_evidence: UgcSnippet[]
  risk_warning?: string | null
  transport_to_next?: Transport | null
  latitude: number
  longitude: number
  category: string
  score_breakdown: Record<string, number>
  estimated_queue_min?: number | null
  estimated_cost?: number | null
}

export interface DroppedPoi {
  poi_id: string
  poi_name: string
  reason: string
}

export interface PlanSummary {
  total_duration_min: number
  total_cost: number
  poi_count: number
  style_highlights: string[]
  tradeoffs: string[]
  dropped_pois: DroppedPoi[]
  total_queue_min: number
  walking_distance_meters: number
  validation: {
    is_valid: boolean
    issues: Array<{ code: string; message: string; severity: string; target?: string | null }>
    repaired_count: number
  }
}

export interface AlternativePoi {
  poi_id: string
  poi_name: string
  category: string
  replace_stop_index?: number | null
  why_candidate: string
  delta_minutes: number
  estimated_queue_min?: number | null
  estimated_cost?: number | null
  score_breakdown: Record<string, number>
}

export interface RefinedPlan {
  plan_id: string
  style: string
  title: string
  description: string
  stops: RefinedStop[]
  summary: PlanSummary
  alternative_pois: AlternativePoi[]
}

export interface PlanResponse {
  plans: RefinedPlan[]
}

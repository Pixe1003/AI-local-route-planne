import type { TimeWindow } from "./pool"

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
  context: PlanContext
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
}

export interface RefinedPlan {
  plan_id: string
  style: string
  title: string
  description: string
  stops: RefinedStop[]
  summary: PlanSummary
}

export interface PlanResponse {
  plans: RefinedPlan[]
}

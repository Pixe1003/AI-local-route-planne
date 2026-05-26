import type { UserNeedProfile } from "./onboarding"
import type { PreferenceSnapshot } from "./preferences"

export interface TimeWindow {
  start: string
  end: string
}

export interface PoolRequest {
  user_id: string
  city: string
  date: string
  time_window: TimeWindow
  persona_tags: string[]
  pace_style?: string
  party?: string
  budget_per_person?: number
  free_text?: string
  need_profile?: UserNeedProfile
  preference_snapshot?: PreferenceSnapshot
  origin_latitude?: number
  origin_longitude?: number
  radius_meters?: number
}

export interface EvidenceSnippet {
  doc_id: string
  source_type: "poi_profile" | "ugc_review" | "fts" | "feature_bucket" | string
  text: string
  score: number
}

export interface PoiInPool {
  id: string
  name: string
  category: string
  latitude: number
  longitude: number
  rating: number
  price_per_person?: number | null
  cover_image?: string | null
  distance_meters?: number | null
  why_recommend: string
  highlight_quote?: string | null
  keywords: string[]
  estimated_queue_min?: number | null
  suitable_score: number
  score_breakdown: Record<string, number>
  retrieval_score?: number | null
  retrieval_provenance: string[]
  evidence_snippets: EvidenceSnippet[]
}

export interface PoolCategory {
  name: string
  description: string
  pois: PoiInPool[]
}

export interface PoolMeta {
  total_count: number
  generated_at: string
  user_persona_summary: string
  data_warning?: string | null
}

export interface PoolResponse {
  pool_id: string
  categories: PoolCategory[]
  default_selected_ids: string[]
  meta: PoolMeta
}

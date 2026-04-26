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
}

export interface PoiInPool {
  id: string
  name: string
  category: string
  rating: number
  price_per_person?: number | null
  cover_image?: string | null
  distance_meters?: number | null
  why_recommend: string
  highlight_quote?: string | null
  keywords: string[]
  estimated_queue_min?: number | null
  suitable_score: number
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
}

export interface PoolResponse {
  pool_id: string
  categories: PoolCategory[]
  default_selected_ids: string[]
  meta: PoolMeta
}

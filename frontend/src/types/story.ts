export type StoryRole = "opener" | "midway" | "main" | "rest" | "closer"

export interface StoryStop {
  poi_id: string
  role: StoryRole
  why: string
  ugc_quote_ref: string
  ugc_quote: string
  suggested_dwell_min: number
}

export interface StoryPlan {
  theme: string
  narrative: string
  stops: StoryStop[]
  dropped: Array<{ poi_id: string; reason: string }>
  fallback_used: boolean
}

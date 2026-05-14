export interface UserFacts {
  user_id: string
  typical_budget_range?: [number, number] | null
  typical_party_type?: string | null
  typical_time_windows: string[]
  favorite_districts: string[]
  favorite_categories: string[]
  avoid_categories: string[]
  rejected_poi_ids: string[]
  session_count: number
  updated_at: string
}

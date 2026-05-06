import type { UserNeedProfile } from "./onboarding"
import type { PlanContext, RefinedPlan } from "./plan"

export interface TripSummary {
  trip_id: string
  title: string
  city: string
  date: string
  active_version_id: string
  version_count: number
  updated_at: string
  cover_poi_names: string[]
}

export interface RouteVersion {
  version_id: string
  plans: RefinedPlan[]
  active_plan_id: string
  source: string
  created_at: string
  user_message?: string | null
  pool_id?: string | null
  selected_poi_ids: string[]
}

export interface TripRecord {
  trip_id: string
  user_id: string
  profile: UserNeedProfile
  planning_context: PlanContext
  versions: RouteVersion[]
  active_version_id: string
  summary: TripSummary
}

export interface SaveRouteVersionRequest {
  trip_id?: string | null
  user_id: string
  profile: UserNeedProfile
  planning_context: PlanContext
  plans: RefinedPlan[]
  active_plan_id: string
  pool_id?: string | null
  selected_poi_ids: string[]
  source: string
  user_message?: string | null
}

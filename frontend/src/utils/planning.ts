import type { UserNeedProfile } from "../types/onboarding"
import type { PlanContext } from "../types/plan"

export const DEFAULT_CITY = "hefei"

export interface OriginInput {
  latitude?: number | null
  longitude?: number | null
  radiusMeters?: number | null
}

export function planningContextFromProfile(
  profile: UserNeedProfile,
  origin?: OriginInput
): PlanContext {
  return {
    city: profile.destination.city || DEFAULT_CITY,
    date: profile.date,
    time_window: {
      start: profile.time.start_time || "13:00",
      end: profile.time.end_time || "21:00"
    },
    party: profile.party_type ?? undefined,
    budget_per_person: profile.budget.budget_per_person ?? undefined,
    origin_latitude: origin?.latitude ?? undefined,
    origin_longitude: origin?.longitude ?? undefined,
    radius_meters: origin?.radiusMeters ?? undefined
  }
}

export function cityLabel(city: string): string {
  return { hefei: "合肥", shanghai: "上海", nanjing: "南京" }[city] ?? city
}

export function versionSourceLabel(source: string): string {
  return {
    direct_plan: "直接规划",
    initial_plan: "推荐池规划",
    chat_adjustment: "对话调整"
  }[source] ?? source
}

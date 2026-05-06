import type { UserNeedProfile } from "../types/onboarding"
import type { PlanContext } from "../types/plan"

export function planningContextFromProfile(profile: UserNeedProfile): PlanContext {
  return {
    city: profile.destination.city || "shanghai",
    date: profile.date,
    time_window: {
      start: profile.time.start_time || "13:00",
      end: profile.time.end_time || "21:00"
    },
    party: profile.party_type ?? undefined,
    budget_per_person: profile.budget.budget_per_person ?? undefined
  }
}

export function cityLabel(city: string): string {
  return { shanghai: "上海", nanjing: "南京" }[city] ?? city
}

export function versionSourceLabel(source: string): string {
  return {
    direct_plan: "直接规划",
    initial_plan: "推荐池规划",
    chat_adjustment: "对话调整"
  }[source] ?? source
}

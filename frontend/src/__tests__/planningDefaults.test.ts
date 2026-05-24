import { describe, expect, it } from "vitest"

import { DEFAULT_CITY, cityLabel, planningContextFromProfile } from "../utils/planning"
import type { UserNeedProfile } from "../types/onboarding"

describe("planning defaults", () => {
  it("uses Hefei as the default city for real RAG data", () => {
    const profile = {
      destination: { city: "" },
      date: "2026-05-02",
      time: {},
      budget: {},
      activity_preferences: [],
      food_preferences: [],
      taste_preferences: [],
      route_style: [],
      avoid: [],
      must_visit: [],
      must_avoid: [],
      completeness_score: 0
    } as UserNeedProfile

    expect(DEFAULT_CITY).toBe("hefei")
    expect(planningContextFromProfile(profile).city).toBe("hefei")
    expect(cityLabel("hefei")).toBe("合肥")
  })
})

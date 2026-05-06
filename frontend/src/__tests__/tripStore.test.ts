import { describe, expect, it, vi, beforeEach } from "vitest"

import { useTripStore } from "../store/tripStore"
import type { SaveRouteVersionRequest, TripRecord, TripSummary } from "../types/trip"

const summary: TripSummary = {
  trip_id: "trip_demo",
  title: "上海 · 2026-05-02 · 情侣出行",
  city: "shanghai",
  date: "2026-05-02",
  active_version_id: "version_1",
  version_count: 1,
  updated_at: "2026-05-05T12:00:00Z",
  cover_poi_names: ["外滩", "豫园"]
}

const updatedSummary: TripSummary = {
  ...summary,
  active_version_id: "version_2",
  version_count: 2,
  updated_at: "2026-05-05T12:30:00Z"
}

const trip = {
  trip_id: "trip_demo",
  user_id: "mock_user",
  summary: updatedSummary,
  active_version_id: "version_2",
  versions: [],
  profile: {
    user_id: "mock_user",
    destination: { city: "shanghai" },
    time: { start_time: "14:00", end_time: "20:00" },
    date: "2026-05-02",
    activity_preferences: [],
    food_preferences: [],
    taste_preferences: [],
    party_type: "couple",
    budget: { budget_per_person: 180, strict: false },
    route_style: [],
    avoid: [],
    must_visit: [],
    must_avoid: [],
    completeness_score: 1
  },
  planning_context: {
    city: "shanghai",
    date: "2026-05-02",
    time_window: { start: "14:00", end: "20:00" },
    party: "couple",
    budget_per_person: 180
  }
} as TripRecord

const listTrips = vi.fn()
const saveRouteVersion = vi.fn()

vi.mock("../api/trips", () => ({
  listTrips: (userId: string) => listTrips(userId),
  getTrip: vi.fn(),
  saveRouteVersion: (request: SaveRouteVersionRequest) => saveRouteVersion(request)
}))

describe("tripStore", () => {
  beforeEach(() => {
    useTripStore.setState({ trips: [], currentTrip: null, loading: false, error: null })
    listTrips.mockReset()
    saveRouteVersion.mockReset()
  })

  it("loads summaries and replaces the saved trip summary after version save", async () => {
    listTrips.mockResolvedValue([summary])
    saveRouteVersion.mockResolvedValue(trip)

    await useTripStore.getState().fetchTrips("mock_user")
    expect(useTripStore.getState().trips).toEqual([summary])

    await useTripStore.getState().saveVersion({} as SaveRouteVersionRequest)
    expect(useTripStore.getState().currentTrip?.trip_id).toBe("trip_demo")
    expect(useTripStore.getState().trips).toEqual([updatedSummary])
  })
})

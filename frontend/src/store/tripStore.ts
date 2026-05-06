import { create } from "zustand"

import { getTrip, listTrips, saveRouteVersion } from "../api/trips"
import type { SaveRouteVersionRequest, TripRecord, TripSummary } from "../types/trip"

interface TripStore {
  trips: TripSummary[]
  currentTrip: TripRecord | null
  loading: boolean
  error: string | null
  fetchTrips: (userId: string) => Promise<TripSummary[]>
  fetchTrip: (tripId: string) => Promise<TripRecord | null>
  saveVersion: (request: SaveRouteVersionRequest) => Promise<TripRecord | null>
  setCurrentTrip: (trip: TripRecord | null) => void
}

export const useTripStore = create<TripStore>((set, get) => ({
  trips: [],
  currentTrip: null,
  loading: false,
  error: null,
  fetchTrips: async userId => {
    set({ loading: true, error: null })
    try {
      const trips = await listTrips(userId)
      set({ trips, loading: false })
      return trips
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : "行程列表读取失败"
      })
      return get().trips
    }
  },
  fetchTrip: async tripId => {
    set({ loading: true, error: null })
    try {
      const trip = await getTrip(tripId)
      set({ currentTrip: trip, loading: false })
      return trip
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : "行程详情读取失败"
      })
      return null
    }
  },
  saveVersion: async request => {
    set({ loading: true, error: null })
    try {
      const trip = await saveRouteVersion(request)
      set(state => ({
        currentTrip: trip,
        loading: false,
        trips: [trip.summary, ...state.trips.filter(item => item.trip_id !== trip.trip_id)]
      }))
      return trip
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : "行程版本保存失败"
      })
      return null
    }
  },
  setCurrentTrip: trip => set({ currentTrip: trip })
}))

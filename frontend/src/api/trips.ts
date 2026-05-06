import { apiClient } from "./client"
import type { SaveRouteVersionRequest, TripRecord, TripSummary } from "../types/trip"

export async function listTrips(userId: string): Promise<TripSummary[]> {
  return apiClient.get<TripSummary[], TripSummary[]>("/trips", {
    params: { user_id: userId }
  })
}

export async function getTrip(tripId: string): Promise<TripRecord> {
  return apiClient.get<TripRecord, TripRecord>(`/trips/${tripId}`)
}

export async function saveRouteVersion(request: SaveRouteVersionRequest): Promise<TripRecord> {
  return apiClient.post<TripRecord, TripRecord>("/trips/versions", request)
}

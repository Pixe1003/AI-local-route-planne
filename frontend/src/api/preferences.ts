import { apiClient } from "./client"
import type { PreferenceSnapshot, PreferenceSnapshotRequest } from "../types/preferences"

export async function buildPreferenceSnapshot(
  request: PreferenceSnapshotRequest
): Promise<PreferenceSnapshot> {
  return apiClient.post<PreferenceSnapshot, PreferenceSnapshot>("/preferences/snapshot", request)
}

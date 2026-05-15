import { apiClient } from "./client"
import type { PoolRequest, PoolResponse } from "../types/pool"

export async function generatePool(request: PoolRequest): Promise<PoolResponse> {
  return apiClient.post<PoolResponse, PoolResponse>("/pool/generate", request)
}

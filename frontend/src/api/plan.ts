import { apiClient } from "./client"
import type { PlanRequest, PlanResponse } from "../types/plan"

export async function generatePlans(request: PlanRequest): Promise<PlanResponse> {
  return apiClient.post<PlanResponse, PlanResponse>("/plan/generate", request)
}

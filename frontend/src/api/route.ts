import { apiClient } from "./client"
import type { RouteChainRequest, RouteChainResponse } from "../types/route"

export async function createRouteChain(request: RouteChainRequest): Promise<RouteChainResponse> {
  return apiClient.post<RouteChainResponse, RouteChainResponse>("/route/chain", request)
}

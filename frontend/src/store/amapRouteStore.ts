import { create } from "zustand"

import type { AmapRouteRequest } from "../types/route"

interface AmapRouteStore {
  routeRequest: AmapRouteRequest | null
  setRouteRequest: (request: AmapRouteRequest) => void
  clearRouteRequest: () => void
}

export const useAmapRouteStore = create<AmapRouteStore>(set => ({
  routeRequest: null,
  setRouteRequest: request => set({ routeRequest: request }),
  clearRouteRequest: () => set({ routeRequest: null })
}))

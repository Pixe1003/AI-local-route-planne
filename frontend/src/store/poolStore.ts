import { create } from "zustand"

import { generatePool } from "../api/pool"
import type { PoolRequest, PoolResponse } from "../types/pool"

interface PoolStore {
  pool: PoolResponse | null
  selectedIds: Set<string>
  loading: boolean
  error: string | null
  fetchPool: (request: PoolRequest) => Promise<PoolResponse | null>
  toggleSelection: (poiId: string) => void
  clearSelection: () => void
}

export const usePoolStore = create<PoolStore>((set, get) => ({
  pool: null,
  selectedIds: new Set<string>(),
  loading: false,
  error: null,
  fetchPool: async request => {
    set({ loading: true, error: null })
    try {
      const pool = await generatePool(request)
      set({ pool, selectedIds: new Set(pool.default_selected_ids), loading: false })
      return pool
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : "推荐池生成失败"
      })
      return null
    }
  },
  toggleSelection: poiId => {
    const next = new Set(get().selectedIds)
    if (next.has(poiId)) {
      next.delete(poiId)
    } else {
      next.add(poiId)
    }
    set({ selectedIds: next })
  },
  clearSelection: () => set({ selectedIds: new Set<string>() })
}))

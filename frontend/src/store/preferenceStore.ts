import { create } from "zustand"

import { buildPreferenceSnapshot } from "../api/preferences"
import type { PreferenceSnapshot, PreferenceSnapshotRequest } from "../types/preferences"
import type { UgcFeedItem } from "../types/ugc"

const LIKE_STORAGE_KEY = "airoute.likes"
const ITEM_STORAGE_KEY = "airoute.likedItems"

interface PreferenceStore {
  likedPoiIds: string[]
  likedItems: Record<string, UgcFeedItem>
  snapshot: PreferenceSnapshot | null
  loading: boolean
  error: string | null
  isLiked: (poiId: string) => boolean
  toggleLike: (item: UgcFeedItem) => void
  snapshotRequest: (userId: string, city?: string) => PreferenceSnapshotRequest
  syncSnapshot: (userId: string, city?: string) => Promise<PreferenceSnapshot | null>
  clearLikes: () => void
}

const readJson = <T,>(key: string, fallback: T): T => {
  try {
    const raw = window.localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

const initialLikedIds = (): string[] =>
  typeof window === "undefined" ? [] : readJson<string[]>(LIKE_STORAGE_KEY, [])

const initialLikedItems = (): Record<string, UgcFeedItem> =>
  typeof window === "undefined" ? {} : readJson<Record<string, UgcFeedItem>>(ITEM_STORAGE_KEY, {})

const persist = (likedPoiIds: string[], likedItems: Record<string, UgcFeedItem>) => {
  window.localStorage.setItem(LIKE_STORAGE_KEY, JSON.stringify(likedPoiIds))
  window.localStorage.setItem(ITEM_STORAGE_KEY, JSON.stringify(likedItems))
}

export const usePreferenceStore = create<PreferenceStore>((set, get) => ({
  likedPoiIds: initialLikedIds(),
  likedItems: initialLikedItems(),
  snapshot: null,
  loading: false,
  error: null,
  isLiked: poiId => get().likedPoiIds.includes(poiId),
  toggleLike: item => {
    const likedPoiIds = get().likedPoiIds.includes(item.poi_id)
      ? get().likedPoiIds.filter(poiId => poiId !== item.poi_id)
      : [...get().likedPoiIds, item.poi_id]
    const likedItems = { ...get().likedItems }
    if (likedPoiIds.includes(item.poi_id)) {
      likedItems[item.poi_id] = item
    } else {
      delete likedItems[item.poi_id]
    }
    persist(likedPoiIds, likedItems)
    set({ likedPoiIds, likedItems, snapshot: null })
  },
  snapshotRequest: (userId, city = "shanghai") => ({
    user_id: userId,
    city,
    liked_poi_ids: get().likedPoiIds,
    disliked_poi_ids: []
  }),
  syncSnapshot: async (userId, city = "shanghai") => {
    set({ loading: true, error: null })
    try {
      const snapshot = await buildPreferenceSnapshot(get().snapshotRequest(userId, city))
      set({ snapshot, loading: false })
      return snapshot
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : "偏好快照生成失败"
      })
      return null
    }
  },
  clearLikes: () => {
    persist([], {})
    set({ likedPoiIds: [], likedItems: {}, snapshot: null })
  }
}))

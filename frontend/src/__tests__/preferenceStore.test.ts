import { beforeEach, describe, expect, it } from "vitest"

import { usePreferenceStore } from "../store/preferenceStore"
import type { UgcFeedItem } from "../types/ugc"

const poi: UgcFeedItem = {
  post_id: "ugc_sh_poi_001",
  poi_id: "sh_poi_001",
  poi_name: "淮海路本帮菜馆",
  title: "今晚这家本地菜很稳",
  source: "xiaohongshu",
  author: "本地体验官01",
  cover_image: "https://example.com/cover.jpg",
  quote: "下午人会少一些。",
  tags: ["美食", "本地口味"],
  category: "restaurant",
  rating: 4.7,
  price_per_person: 64,
  estimated_queue_min: 15,
  city: "shanghai"
}

describe("preferenceStore", () => {
  beforeEach(() => {
    window.localStorage.clear()
    usePreferenceStore.setState({
      likedPoiIds: [],
      likedItems: {},
      snapshot: null,
      loading: false,
      error: null
    })
  })

  it("toggles liked UGC cards and persists them to localStorage", () => {
    usePreferenceStore.getState().toggleLike(poi)
    expect(usePreferenceStore.getState().likedPoiIds).toEqual(["sh_poi_001"])
    expect(JSON.parse(window.localStorage.getItem("airoute.likes") ?? "[]")).toEqual(["sh_poi_001"])

    usePreferenceStore.getState().toggleLike(poi)
    expect(usePreferenceStore.getState().likedPoiIds).toEqual([])
    expect(JSON.parse(window.localStorage.getItem("airoute.likes") ?? "[]")).toEqual([])
  })

  it("builds a local request payload from liked POIs", () => {
    usePreferenceStore.getState().toggleLike(poi)

    expect(usePreferenceStore.getState().snapshotRequest("mock_user")).toEqual({
      user_id: "mock_user",
      city: "hefei",
      liked_poi_ids: ["sh_poi_001"],
      disliked_poi_ids: []
    })
  })
})

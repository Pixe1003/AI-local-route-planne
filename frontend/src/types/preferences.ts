export interface PreferenceSnapshotRequest {
  user_id: string
  liked_poi_ids: string[]
  disliked_poi_ids: string[]
  city: string
}

export interface PreferenceSnapshot {
  user_id: string
  liked_poi_ids: string[]
  disliked_poi_ids: string[]
  tag_weights: Record<string, number>
  category_weights: Record<string, number>
  keyword_weights: Record<string, number>
  source: "ugc_feed_mock"
}

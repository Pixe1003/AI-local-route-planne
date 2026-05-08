import { apiClient } from "./client"
import type { UgcFeedItem } from "../types/ugc"

export async function fetchUgcFeed(city = "shanghai"): Promise<UgcFeedItem[]> {
  return apiClient.get<UgcFeedItem[], UgcFeedItem[]>("/ugc/feed", { params: { city } })
}

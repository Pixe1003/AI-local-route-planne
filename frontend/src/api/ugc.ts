import { apiClient } from "./client"
import type { UgcFeedItem } from "../types/ugc"
import { DEFAULT_CITY } from "../utils/planning"

export async function fetchUgcFeed(city = DEFAULT_CITY): Promise<UgcFeedItem[]> {
  return apiClient.get<UgcFeedItem[], UgcFeedItem[]>("/ugc/feed", { params: { city } })
}

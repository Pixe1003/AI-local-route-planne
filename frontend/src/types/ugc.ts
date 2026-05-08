export interface UgcFeedItem {
  post_id: string
  poi_id: string
  poi_name: string
  title: string
  source: string
  author: string
  cover_image?: string | null
  quote: string
  tags: string[]
  category: string
  rating: number
  price_per_person?: number | null
  estimated_queue_min?: number | null
  city: string
}

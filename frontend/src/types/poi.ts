export interface PoiDetail {
  id: string
  name: string
  city: string
  category: string
  address: string
  latitude: number
  longitude: number
  rating: number
  price_per_person?: number | null
  tags: string[]
  cover_image?: string | null
}

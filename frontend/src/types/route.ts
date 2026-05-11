export type RouteMode = "walking" | "driving"

export interface RoutePoi {
  id: string
  name: string
  longitude: number
  latitude: number
  category?: string | null
  cover_image?: string | null
}

export interface RouteChainRequest {
  mode: RouteMode
  pois?: RoutePoi[]
  poi_ids?: string[]
}

export interface RouteSegmentSummary {
  segment_index: number
  from_poi_id: string
  from_poi_name: string
  to_poi_id: string
  to_poi_name: string
  distance_m: number
  duration_s: number
}

export interface RouteStepFeatureProperties {
  segment_index: number
  step_index: number
  from_poi_id: string
  from_poi_name: string
  to_poi_id: string
  to_poi_name: string
  instruction?: string | null
  road_name?: string | null
  distance_m: number
  duration_s?: number | null
}

export interface GeoJSONLineString {
  type: "LineString"
  coordinates: [number, number][]
}

export interface GeoJSONFeature {
  type: "Feature"
  properties: RouteStepFeatureProperties
  geometry: GeoJSONLineString
}

export interface GeoJSONFeatureCollection {
  type: "FeatureCollection"
  features: GeoJSONFeature[]
}

export interface RouteChainResponse {
  mode: RouteMode
  ordered_pois: RoutePoi[]
  total_distance_m: number
  total_duration_s: number
  segments: RouteSegmentSummary[]
  geojson: GeoJSONFeatureCollection
}

export interface AmapRouteRequest {
  mode: RouteMode
  poi_ids: string[]
  source: "ugc_instant_route" | "manual_route"
  pool_id?: string
  free_text?: string
  date?: string
  time_window?: {
    start: string
    end: string
  }
}

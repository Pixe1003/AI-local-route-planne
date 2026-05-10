export type PoiPoint = {
  id: string;
  name: string;
  longitude: number;
  latitude: number;
  type?: string;
};

export type RouteMode = "walking" | "driving";

export type RouteChainRequest = {
  mode: RouteMode;
  pois: PoiPoint[];
};

export type RouteSegment = {
  segment_index: number;
  from_poi_id: string;
  from_poi_name: string;
  to_poi_id: string;
  to_poi_name: string;
  distance_m: number;
  duration_s: number;
};

export type GeoJSONLineStringFeature = {
  type: "Feature";
  properties: {
    segment_index: number;
    step_index: number;
    from_poi_id: string;
    from_poi_name: string;
    to_poi_id: string;
    to_poi_name: string;
    instruction?: string | null;
    road_name?: string | null;
    distance_m: number;
    duration_s?: number | null;
  };
  geometry: {
    type: "LineString";
    coordinates: [number, number][];
  };
};

export type GeoJSONFeatureCollection = {
  type: "FeatureCollection";
  features: GeoJSONLineStringFeature[];
};

export type RouteChainResponse = {
  mode: RouteMode;
  ordered_pois: PoiPoint[];
  total_distance_m: number;
  total_duration_s: number;
  segments: RouteSegment[];
  geojson: GeoJSONFeatureCollection;
};

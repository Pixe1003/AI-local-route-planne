"use client";

import { useEffect } from "react";

import type {
  AMapMapInstance,
  AMapOverlayInstance,
  AMapPolylineInstance,
} from "@/lib/load-amap";
import type { GeoJSONFeatureCollection } from "@/lib/route-types";

type RoutePolylineLayerProps = {
  map: AMapMapInstance | null;
  geojson: GeoJSONFeatureCollection | null;
};

export default function RoutePolylineLayer({
  map,
  geojson,
}: RoutePolylineLayerProps) {
  useEffect(() => {
    const AMap = window.AMap;
    if (!map || !AMap || !geojson) {
      return;
    }

    const polylines: AMapPolylineInstance[] = geojson.features
      .filter((feature) => feature.geometry.type === "LineString")
      .map(
        (feature) =>
          new AMap.Polyline({
            map,
            path: feature.geometry.coordinates,
            strokeColor: "#2563eb",
            strokeOpacity: 0.9,
            strokeWeight: 6,
            lineJoin: "round",
            zIndex: 80,
          }),
      );

    if (polylines.length > 0) {
      map.setFitView(polylines as AMapOverlayInstance[]);
    }

    return () => {
      polylines.forEach((polyline) => polyline.setMap(null));
    };
  }, [geojson, map]);

  return null;
}

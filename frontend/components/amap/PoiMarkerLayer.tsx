"use client";

import { useEffect } from "react";

import type { AMapMarkerInstance, AMapMapInstance } from "@/lib/load-amap";
import type { PoiPoint } from "@/lib/route-types";

type PoiMarkerLayerProps = {
  map: AMapMapInstance | null;
  pois: PoiPoint[];
  selectedPoiIds: string[];
  onPoiClick: (poi: PoiPoint) => void;
};

export default function PoiMarkerLayer({
  map,
  pois,
  selectedPoiIds,
  onPoiClick,
}: PoiMarkerLayerProps) {
  useEffect(() => {
    const AMap = window.AMap;
    if (!map || !AMap) {
      return;
    }

    const selectedSet = new Set(selectedPoiIds);
    const markers: AMapMarkerInstance[] = pois.map((poi) => {
      const isSelected = selectedSet.has(poi.id);
      const marker = new AMap.Marker({
        map,
        position: [poi.longitude, poi.latitude],
        title: poi.name,
        content: `<button class="poi-marker${isSelected ? " selected" : ""}" type="button">${poi.name}</button>`,
      });

      marker.on("click", () => {
        onPoiClick(poi);
      });

      return marker;
    });

    return () => {
      markers.forEach((marker) => marker.setMap(null));
    };
  }, [map, onPoiClick, pois, selectedPoiIds]);

  return null;
}

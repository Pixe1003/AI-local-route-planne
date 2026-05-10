"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import PoiMarkerLayer from "@/components/amap/PoiMarkerLayer";
import RoutePolylineLayer from "@/components/amap/RoutePolylineLayer";
import { loadAmap } from "@/lib/load-amap";
import type { AMapMapInstance } from "@/lib/load-amap";
import type { GeoJSONFeatureCollection, PoiPoint } from "@/lib/route-types";

const NANJING_CENTER: [number, number] = [118.7969, 32.0603];

type LoadStatus = "idle" | "loading" | "ready" | "error";

type AmapMapProps = {
  pois: PoiPoint[];
  selectedPoiIds: string[];
  routeGeojson: GeoJSONFeatureCollection | null;
  onPoiSelect: (poi: PoiPoint) => void;
};

export default function AmapMap({
  pois,
  selectedPoiIds,
  routeGeojson,
  onPoiSelect,
}: AmapMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<AMapMapInstance | null>(null);
  const [map, setMap] = useState<AMapMapInstance | null>(null);
  const [status, setStatus] = useState<LoadStatus>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const envStatus = useMemo(
    () => ({
      hasJsKey: Boolean(process.env.NEXT_PUBLIC_AMAP_JS_KEY),
      hasSecurityJsCode: Boolean(process.env.NEXT_PUBLIC_AMAP_SECURITY_JS_CODE),
      hasApiBaseUrl: Boolean(process.env.NEXT_PUBLIC_API_BASE_URL),
    }),
    [],
  );

  useEffect(() => {
    const jsKey = process.env.NEXT_PUBLIC_AMAP_JS_KEY;
    const securityJsCode = process.env.NEXT_PUBLIC_AMAP_SECURITY_JS_CODE;

    if (!jsKey) {
      setStatus("error");
      setErrorMessage("Missing NEXT_PUBLIC_AMAP_JS_KEY.");
      return;
    }

    if (!securityJsCode) {
      setStatus("error");
      setErrorMessage("Missing NEXT_PUBLIC_AMAP_SECURITY_JS_CODE.");
      return;
    }

    if (!containerRef.current) {
      return;
    }

    let cancelled = false;
    setStatus("loading");
    setErrorMessage(null);

    loadAmap({ jsKey, securityJsCode })
      .then((AMap) => {
        if (cancelled || !containerRef.current) {
          return;
        }

        mapRef.current?.destroy();
        const nextMap = new AMap.Map(containerRef.current, {
          center: NANJING_CENTER,
          zoom: 12,
          viewMode: "2D",
        });
        mapRef.current = nextMap;
        setMap(nextMap);
        setStatus("ready");
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }

        setStatus("error");
        setErrorMessage(
          error instanceof Error ? error.message : "Failed to load AMap JS API.",
        );
      });

    return () => {
      cancelled = true;
      mapRef.current?.destroy();
      mapRef.current = null;
      setMap(null);
    };
  }, []);

  return (
    <div className="route-map-shell">
      <div ref={containerRef} className="amap-container" aria-label="AMap map" />
      <PoiMarkerLayer
        map={map}
        pois={pois}
        selectedPoiIds={selectedPoiIds}
        onPoiClick={onPoiSelect}
      />
      <RoutePolylineLayer map={map} geojson={routeGeojson} />
      {status !== "ready" ? (
        <div className="map-status" role="status">
          <strong>{status === "loading" ? "Loading map" : "Map not ready"}</strong>
          <span>{errorMessage ?? "Preparing AMap JS API 2.0."}</span>
        </div>
      ) : null}
      <div className="map-env-badge" aria-label="Environment status">
        <span className={envStatus.hasJsKey ? "ok" : "missing"}>
          JS Key {envStatus.hasJsKey ? "configured" : "missing"}
        </span>
        <span className={envStatus.hasSecurityJsCode ? "ok" : "missing"}>
          Security code {envStatus.hasSecurityJsCode ? "configured" : "missing"}
        </span>
        <span className={envStatus.hasApiBaseUrl ? "ok" : "missing"}>
          API URL {envStatus.hasApiBaseUrl ? "configured" : "missing"}
        </span>
      </div>
    </div>
  );
}

"use client";

import { useCallback, useMemo, useState } from "react";

import AmapMap from "@/components/amap/AmapMap";
import RouteSidebar from "@/components/route/RouteSidebar";
import { mockPois } from "@/lib/mock-pois";
import { createRouteChain } from "@/lib/route-api";
import type {
  PoiPoint,
  RouteChainResponse,
  RouteMode,
} from "@/lib/route-types";

export default function RouteMapPage() {
  const [mode, setMode] = useState<RouteMode>("walking");
  const [selectedPois, setSelectedPois] = useState<PoiPoint[]>([]);
  const [routeResult, setRouteResult] = useState<RouteChainResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const apiBaseUrlConfigured = Boolean(process.env.NEXT_PUBLIC_API_BASE_URL);
  const selectedPoiIds = useMemo(
    () => selectedPois.map((poi) => poi.id),
    [selectedPois],
  );

  const handlePoiSelect = useCallback((poi: PoiPoint) => {
    setSelectedPois((currentPois) => {
      if (currentPois.some((selectedPoi) => selectedPoi.id === poi.id)) {
        return currentPois;
      }

      return [...currentPois, poi];
    });
    setErrorMessage(null);
  }, []);

  const handleRemovePoi = useCallback((poiId: string) => {
    setSelectedPois((currentPois) =>
      currentPois.filter((poi) => poi.id !== poiId),
    );
    setRouteResult(null);
    setErrorMessage(null);
  }, []);

  const handleClear = useCallback(() => {
    setSelectedPois([]);
    setRouteResult(null);
    setErrorMessage(null);
  }, []);

  const handleGenerateRoute = useCallback(async () => {
    if (selectedPois.length < 2) {
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);

    try {
      const result = await createRouteChain({
        mode,
        pois: selectedPois,
      });
      setRouteResult(result);
      if (result.geojson.features.length === 0) {
        setErrorMessage("No route was returned.");
      }
    } catch (error: unknown) {
      setRouteResult(null);
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to generate route.",
      );
    } finally {
      setIsLoading(false);
    }
  }, [mode, selectedPois]);

  return (
    <main className="route-map-page">
      <section className="route-map-main" aria-label="Map area">
        <AmapMap
          pois={mockPois}
          selectedPoiIds={selectedPoiIds}
          routeGeojson={routeResult?.geojson ?? null}
          onPoiSelect={handlePoiSelect}
        />
      </section>
      <RouteSidebar
        mode={mode}
        onModeChange={setMode}
        selectedPois={selectedPois}
        onRemovePoi={handleRemovePoi}
        onClear={handleClear}
        onGenerateRoute={handleGenerateRoute}
        routeResult={routeResult}
        isLoading={isLoading}
        errorMessage={errorMessage}
        apiBaseUrlConfigured={apiBaseUrlConfigured}
      />
    </main>
  );
}

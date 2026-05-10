"use client";

import type {
  PoiPoint,
  RouteChainResponse,
  RouteMode,
} from "@/lib/route-types";

type RouteSidebarProps = {
  mode: RouteMode;
  onModeChange: (mode: RouteMode) => void;
  selectedPois: PoiPoint[];
  onRemovePoi: (poiId: string) => void;
  onClear: () => void;
  onGenerateRoute: () => void;
  routeResult: RouteChainResponse | null;
  isLoading: boolean;
  errorMessage: string | null;
  apiBaseUrlConfigured: boolean;
};

export default function RouteSidebar({
  mode,
  onModeChange,
  selectedPois,
  onRemovePoi,
  onClear,
  onGenerateRoute,
  routeResult,
  isLoading,
  errorMessage,
  apiBaseUrlConfigured,
}: RouteSidebarProps) {
  const canGenerate = selectedPois.length >= 2 && !isLoading && apiBaseUrlConfigured;

  return (
    <aside className="route-map-panel" aria-label="Route planning panel">
      <div>
        <p className="panel-kicker">Route Map</p>
        <h1>POI Route Planning</h1>
        <p>Click POI markers on the map to build a walking or driving route.</p>
      </div>

      <section className="panel-section">
        <h2>Mode</h2>
        <div className="mode-switch" role="group" aria-label="Route mode">
          <button
            className={mode === "walking" ? "active" : ""}
            type="button"
            onClick={() => onModeChange("walking")}
          >
            walking
          </button>
          <button
            className={mode === "driving" ? "active" : ""}
            type="button"
            onClick={() => onModeChange("driving")}
          >
            driving
          </button>
        </div>
      </section>

      <section className="panel-section">
        <div className="section-title-row">
          <h2>Selected POIs</h2>
          <button type="button" className="text-button" onClick={onClear}>
            Clear
          </button>
        </div>
        {selectedPois.length > 0 ? (
          <ol className="selected-poi-list">
            {selectedPois.map((poi, index) => (
              <li key={poi.id}>
                <span className="poi-order">{index + 1}</span>
                <span>
                  <strong>{poi.name}</strong>
                  <small>{poi.type ?? "POI"}</small>
                </span>
                <button type="button" onClick={() => onRemovePoi(poi.id)}>
                  Remove
                </button>
              </li>
            ))}
          </ol>
        ) : (
          <p>No POI selected. Click markers on the map.</p>
        )}
        <button
          type="button"
          className="primary-button"
          disabled={!canGenerate}
          onClick={onGenerateRoute}
        >
          {isLoading ? "Generating..." : "Generate route"}
        </button>
      </section>

      {!apiBaseUrlConfigured ? (
        <div className="panel-alert error">Missing NEXT_PUBLIC_API_BASE_URL.</div>
      ) : null}
      {errorMessage ? <div className="panel-alert error">{errorMessage}</div> : null}

      {routeResult ? (
        <section className="panel-section">
          <h2>Route Result</h2>
          <div className="summary-grid">
            <span>
              <strong>{formatDistance(routeResult.total_distance_m)}</strong>
              Total distance
            </span>
            <span>
              <strong>{formatDuration(routeResult.total_duration_s)}</strong>
              Total duration
            </span>
          </div>
          <ol className="segment-list">
            {routeResult.segments.map((segment) => (
              <li key={segment.segment_index}>
                <strong>
                  {segment.from_poi_name} -&gt; {segment.to_poi_name}
                </strong>
                <span>
                  {formatDistance(segment.distance_m)} /{" "}
                  {formatDuration(segment.duration_s)}
                </span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}
    </aside>
  );
}

function formatDistance(distanceM: number) {
  if (distanceM >= 1000) {
    return `${(distanceM / 1000).toFixed(2)} km`;
  }

  return `${Math.round(distanceM)} m`;
}

function formatDuration(durationS: number) {
  const minutes = Math.round(durationS / 60);
  if (minutes < 60) {
    return `${minutes} min`;
  }

  const hours = Math.floor(minutes / 60);
  const restMinutes = minutes % 60;
  return `${hours} h ${restMinutes} min`;
}

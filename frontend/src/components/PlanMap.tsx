import { useEffect, useMemo, useRef, useState } from "react"
import { MapPin } from "lucide-react"

import type { RefinedPlan } from "../types/plan"
import { hasAmapConfig, loadAmap } from "../utils/amapLoader"
import { renderAmapRouteSegments } from "../utils/amapRouteRenderer"

interface PlanMapProps {
  plan: RefinedPlan
  highlightedStopIndex?: number
  onStopClick?: (index: number) => void
}

export function PlanMap({ plan, highlightedStopIndex, onStopClick }: PlanMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<AMap.Map | null>(null)
  const markerButtonsRef = useRef<HTMLButtonElement[]>([])
  const onStopClickRef = useRef(onStopClick)
  const [mode, setMode] = useState<"real" | "fallback">(hasAmapConfig() ? "real" : "fallback")
  const routeKey = useMemo(
    () =>
      plan.stops
        .map(stop => `${stop.poi_id}:${stop.longitude}:${stop.latitude}:${stop.transport_to_next?.mode ?? ""}`)
        .join("|"),
    [plan.stops]
  )

  useEffect(() => {
    onStopClickRef.current = onStopClick
  }, [onStopClick])

  useEffect(() => {
    markerButtonsRef.current.forEach((button, index) => {
      button.classList.toggle("active", highlightedStopIndex === index)
    })
  }, [highlightedStopIndex])

  useEffect(() => {
    if (!hasAmapConfig() || !plan.stops.length) {
      setMode("fallback")
      return
    }

    let disposed = false
    setMode("real")
    loadAmap()
      .then(AMap => {
        if (disposed || !containerRef.current) return
        mapRef.current?.destroy()
        const map = new AMap.Map(containerRef.current, {
          zoom: 12,
          viewMode: "2D"
        })
        mapRef.current = map
        markerButtonsRef.current = []
        const positions = plan.stops.map(stop => [stop.longitude, stop.latitude] as [number, number])

        plan.stops.forEach((stop, index) => {
          const button = document.createElement("button")
          button.className = `amap-stop-marker${highlightedStopIndex === index ? " active" : ""}`
          button.type = "button"
          button.setAttribute("aria-label", stop.poi_name)
          button.textContent = String(index + 1)
          button.addEventListener("click", event => {
            event.stopPropagation()
            onStopClickRef.current?.(index)
          })
          markerButtonsRef.current[index] = button

          const marker = new AMap.Marker({
            position: positions[index],
            anchor: "center",
            content: button
          })
          marker.on("click", () => onStopClickRef.current?.(index))
          map.add(marker)
        })

        renderAmapRouteSegments({ AMap, map, stops: plan.stops, isDisposed: () => disposed })
        map.setFitView()
      })
      .catch(() => {
        if (!disposed) setMode("fallback")
      })

    return () => {
      disposed = true
      mapRef.current?.destroy()
      mapRef.current = null
      markerButtonsRef.current = []
    }
  }, [plan.plan_id, routeKey])

  if (mode === "real") {
    return (
      <div className="map-panel">
        <div className="map-toolbar">
          <MapPin size={18} />
          <span>高德路网规划 · 本地 POI</span>
        </div>
        <div className="real-map" data-testid="amap-container" ref={containerRef} />
      </div>
    )
  }

  return (
    <FallbackMap
      highlightedStopIndex={highlightedStopIndex}
      onStopClick={onStopClick}
      plan={plan}
      title="高德地图未配置 · 本地距离兜底视图"
    />
  )
}

function FallbackMap({
  plan,
  highlightedStopIndex,
  onStopClick,
  title
}: PlanMapProps & { title: string }) {
  if (!plan.stops.length) {
    return (
      <div className="map-panel">
        <div className="map-toolbar">
          <MapPin size={18} />
          <span>{title}</span>
        </div>
        <div className="mock-map empty-map">暂无站点</div>
      </div>
    )
  }
  const minLat = Math.min(...plan.stops.map(stop => stop.latitude))
  const maxLat = Math.max(...plan.stops.map(stop => stop.latitude))
  const minLng = Math.min(...plan.stops.map(stop => stop.longitude))
  const maxLng = Math.max(...plan.stops.map(stop => stop.longitude))

  const position = (lat: number, lng: number) => ({
    left: `${12 + ((lng - minLng) / Math.max(maxLng - minLng, 0.01)) * 76}%`,
    top: `${78 - ((lat - minLat) / Math.max(maxLat - minLat, 0.01)) * 58}%`
  })

  return (
    <div className="map-panel">
      <div className="map-toolbar">
        <MapPin size={18} />
        <span>{title}</span>
      </div>
      <div className="mock-map">
        <svg className="route-line" viewBox="0 0 100 100" preserveAspectRatio="none">
          <polyline
            fill="none"
            points={plan.stops
              .map(stop => {
                const pos = position(stop.latitude, stop.longitude)
                return `${parseFloat(pos.left)} ${parseFloat(pos.top)}`
              })
              .join(" ")}
            stroke="#1677ff"
            strokeDasharray="5 4"
            strokeWidth="1.6"
          />
        </svg>
        {plan.stops.map((stop, index) => (
          <button
            className={highlightedStopIndex === index ? "map-marker active" : "map-marker"}
            key={stop.poi_id}
            onClick={() => onStopClick?.(index)}
            style={position(stop.latitude, stop.longitude)}
            type="button"
          >
            {index + 1}
          </button>
        ))}
      </div>
    </div>
  )
}

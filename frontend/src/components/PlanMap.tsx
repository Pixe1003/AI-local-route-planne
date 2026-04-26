import { MapPin } from "lucide-react"

import type { RefinedPlan } from "../types/plan"

interface PlanMapProps {
  plan: RefinedPlan
  highlightedStopIndex?: number
  onStopClick?: (index: number) => void
}

export function PlanMap({ plan, highlightedStopIndex, onStopClick }: PlanMapProps) {
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
        <span>高德地图 · 本地距离兜底视图</span>
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

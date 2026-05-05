import { ChevronRight } from "lucide-react"
import { useState } from "react"

import type { RefinedPlan } from "../types/plan"

interface PlanTimelineProps {
  plan: RefinedPlan
  onStopClick?: (index: number) => void
}

export function PlanTimeline({ plan, onStopClick }: PlanTimelineProps) {
  const [expanded, setExpanded] = useState<string | null>(plan.stops[0]?.poi_id ?? null)

  return (
    <div className="timeline">
      {plan.stops.map((stop, index) => (
        <div className="timeline-item" key={stop.poi_id}>
          <button
            className="timeline-stop"
            onClick={() => {
              setExpanded(expanded === stop.poi_id ? null : stop.poi_id)
              onStopClick?.(index)
            }}
            type="button"
          >
            <span className="time-block">
              {stop.arrival_time}
              <small>{stop.departure_time}</small>
            </span>
            <span className="stop-main">
              <strong>{stop.poi_name}</strong>
              <em>{stop.why_this_one}</em>
            </span>
            <ChevronRight size={18} />
          </button>
          {expanded === stop.poi_id ? (
            <div className="evidence-panel">
              {stop.score_breakdown ? (
                <div className="score-row">
                  <span>评分 {Math.round(stop.score_breakdown.total ?? 0)}</span>
                  <span>兴趣 {Math.round(stop.score_breakdown.user_interest ?? 0)}</span>
                  <span>UGC {Math.round(stop.score_breakdown.ugc_match ?? 0)}</span>
                </div>
              ) : null}
              {stop.ugc_evidence.map(item => (
                <p key={`${item.source}-${item.quote}`}>“{item.quote}” · {item.source}</p>
              ))}
              {stop.risk_warning ? <strong>{stop.risk_warning}</strong> : null}
            </div>
          ) : null}
          {stop.transport_to_next ? (
            <div className="transport-row">
              {stop.transport_to_next.mode} · {stop.transport_to_next.duration_min} 分钟 ·{" "}
              {stop.transport_to_next.distance_meters} 米
            </div>
          ) : null}
        </div>
      ))}
    </div>
  )
}

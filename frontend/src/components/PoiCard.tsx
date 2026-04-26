import { Check, Clock, Star } from "lucide-react"

import type { PoiInPool } from "../types/pool"

interface PoiCardProps {
  poi: PoiInPool
  selected: boolean
  onToggle: (poiId: string) => void
  showWhyRecommend?: boolean
  compact?: boolean
}

export function PoiCard({
  poi,
  selected,
  onToggle,
  showWhyRecommend = true,
  compact = false
}: PoiCardProps) {
  return (
    <article
      className={selected ? "poi-card selected" : "poi-card"}
      onClick={() => onToggle(poi.id)}
    >
      <div className="poi-image-wrap">
        {selected ? (
          <span className="corner-check">
            <Check size={16} />
          </span>
        ) : null}
        <img alt={poi.name} className="poi-image" src={poi.cover_image ?? ""} />
      </div>
      <div className="poi-card-body">
        <div className="poi-title-row">
          <h3>{poi.name}</h3>
          <span className="rating">
            <Star size={14} /> {poi.rating.toFixed(1)}
          </span>
        </div>
        <div className="poi-meta-row">
          <span>人均 ¥{poi.price_per_person ?? "--"}</span>
          <span>
            <Clock size={13} /> 排队 {poi.estimated_queue_min ?? "--"} 分
          </span>
        </div>
        {showWhyRecommend && !compact ? <p className="why">{poi.why_recommend}</p> : null}
        {!compact && poi.highlight_quote ? <p className="quote">“{poi.highlight_quote}”</p> : null}
        <div className="keyword-row">
          {poi.keywords.slice(0, 3).map(keyword => (
            <span key={keyword}>{keyword}</span>
          ))}
        </div>
      </div>
    </article>
  )
}

import { CalendarClock, ChevronUp, CircleDollarSign, MapPin, Route, Sparkles, Trash2 } from "lucide-react"
import { FormEvent, useState } from "react"

import { PlanParamsDrawer } from "./PlanParamsDrawer"
import type { WeatherCondition } from "../types/pool"
import type { UgcFeedItem } from "../types/ugc"

interface OriginOption {
  id: string
  label: string
}

interface WeatherOption {
  value: WeatherCondition
  label: string
}

interface PlanBasketProps {
  budget: number
  busy: boolean
  date: string
  end: string
  error: string | null
  likedItems: UgcFeedItem[]
  likedPoiCount: number
  onClearLikes: () => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  originId: string
  originOptions: OriginOption[]
  query: string
  radiusMeters: number
  setBudget: (budget: number) => void
  setDate: (date: string) => void
  setEnd: (end: string) => void
  setOriginId: (originId: string) => void
  setQuery: (query: string) => void
  setRadiusMeters: (radiusMeters: number) => void
  setStart: (start: string) => void
  setWeatherCondition: (weatherCondition: WeatherCondition) => void
  start: string
  weatherCondition: WeatherCondition
  weatherOptions: WeatherOption[]
}

export function PlanBasket({
  budget,
  busy,
  date,
  end,
  error,
  likedItems,
  likedPoiCount,
  onClearLikes,
  onSubmit,
  originId,
  originOptions,
  query,
  radiusMeters,
  setBudget,
  setDate,
  setEnd,
  setOriginId,
  setQuery,
  setRadiusMeters,
  setStart,
  setWeatherCondition,
  start,
  weatherCondition,
  weatherOptions
}: PlanBasketProps) {
  const [expanded, setExpanded] = useState(true)
  const summary = likedItems.length
    ? likedItems.map(item => item.poi_name).slice(0, 3).join(" / ")
    : "可直接用自然语言规划，也可以先收藏 UGC 地点"

  return (
    <section className={expanded ? "plan-basket route-intent-card expanded" : "plan-basket route-intent-card"} aria-label="路线需求">
      <button
        aria-expanded={expanded}
        className="plan-basket-toggle"
        onClick={() => setExpanded(value => !value)}
        type="button"
      >
        <span className="basket-count">{likedPoiCount}</span>
        <span>
          <strong>Agent 规划</strong>
          <small>{summary}</small>
        </span>
        <ChevronUp size={18} />
      </button>

      {expanded ? (
        <form className="plan-basket-form" onSubmit={onSubmit}>
          <div className="basket-drawer-grid">
            <div className="basket-query">
              <label>
                <span>路线需求</span>
                <textarea onChange={event => setQuery(event.target.value)} value={query} />
              </label>
              <div className="basket-quick-metrics">
                <span>
                  <CalendarClock size={15} />
                  {start}-{end}
                </span>
                <span>
                  <CircleDollarSign size={15} />
                  ¥{budget}/人
                </span>
              </div>
            </div>

            <PlanParamsDrawer
              budget={budget}
              date={date}
              end={end}
              originId={originId}
              originOptions={originOptions}
              radiusMeters={radiusMeters}
              setBudget={setBudget}
              setDate={setDate}
              setEnd={setEnd}
              setOriginId={setOriginId}
              setRadiusMeters={setRadiusMeters}
              setStart={setStart}
              setWeatherCondition={setWeatherCondition}
              start={start}
              weatherCondition={weatherCondition}
              weatherOptions={weatherOptions}
            />

            <div className="basket-list">
              <div className="basket-section-title">
                <Sparkles size={16} />
                收藏偏好
              </div>
              {likedItems.length ? (
                likedItems.map(item => (
                  <div className="basket-poi" key={item.poi_id}>
                    <MapPin size={15} />
                    <span>{item.poi_name}</span>
                    <small>{item.rating.toFixed(1)} · ¥{item.price_per_person ?? "--"}</small>
                  </div>
                ))
              ) : (
                <p className="basket-empty">收藏会优先进入路线候选池，也可以先直接生成路线。</p>
              )}
              <button className="basket-clear-button" disabled={!likedPoiCount} onClick={onClearLikes} type="button">
                <Trash2 size={15} />
                清空
              </button>
            </div>
          </div>

          {error ? <p className="error-text">{error}</p> : null}
          <button className="basket-submit-button" disabled={busy} type="submit">
            <Route size={18} />
            {busy ? "Agent 规划中" : "生成路线"}
          </button>
        </form>
      ) : null}
    </section>
  )
}

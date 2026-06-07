import type { WeatherCondition } from "../types/pool"

interface OriginOption {
  id: string
  label: string
}

interface WeatherOption {
  value: WeatherCondition
  label: string
}

interface PlanParamsDrawerProps {
  budget: number
  date: string
  end: string
  originId: string
  originOptions: OriginOption[]
  radiusMeters: number
  setBudget: (budget: number) => void
  setDate: (date: string) => void
  setEnd: (end: string) => void
  setOriginId: (originId: string) => void
  setRadiusMeters: (radiusMeters: number) => void
  setStart: (start: string) => void
  setWeatherCondition: (weatherCondition: WeatherCondition) => void
  start: string
  weatherCondition: WeatherCondition
  weatherOptions: WeatherOption[]
}

export function PlanParamsDrawer({
  budget,
  date,
  end,
  originId,
  originOptions,
  radiusMeters,
  setBudget,
  setDate,
  setEnd,
  setOriginId,
  setRadiusMeters,
  setStart,
  setWeatherCondition,
  start,
  weatherCondition,
  weatherOptions
}: PlanParamsDrawerProps) {
  return (
    <div className="plan-params-drawer">
      <label>
        <span>日期</span>
        <input onChange={event => setDate(event.target.value)} type="date" value={date} />
      </label>
      <label>
        <span>开始</span>
        <input onChange={event => setStart(event.target.value)} type="time" value={start} />
      </label>
      <label>
        <span>结束</span>
        <input onChange={event => setEnd(event.target.value)} type="time" value={end} />
      </label>
      <label>
        <span>预算/人</span>
        <input min={0} onChange={event => setBudget(Number(event.target.value))} type="number" value={budget} />
      </label>
      <label>
        <span>出发点</span>
        <select onChange={event => setOriginId(event.target.value)} value={originId}>
          {originOptions.map(item => (
            <option key={item.id} value={item.id}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>天气</span>
        <select
          onChange={event => setWeatherCondition(event.target.value as WeatherCondition)}
          value={weatherCondition}
        >
          {weatherOptions.map(item => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      <label className="plan-radius-field">
        <span>搜索半径 {Math.round(radiusMeters / 1000)} km</span>
        <input
          max={16000}
          min={1000}
          onChange={event => setRadiusMeters(Number(event.target.value))}
          step={500}
          type="range"
          value={radiusMeters}
        />
      </label>
    </div>
  )
}

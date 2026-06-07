import { RotateCcw, SlidersHorizontal } from "lucide-react"

import { useFilterStore } from "../store/filterStore"

interface CategoryOption {
  label: string
  value: string
}

interface MemorySidebarProps {
  categories: CategoryOption[]
  resultCount: number
}

export function MemorySidebar({ categories, resultCount }: MemorySidebarProps) {
  const {
    category,
    maxPrice,
    maxQueue,
    minRating,
    radiusMeters,
    reset,
    setCategory,
    setMaxPrice,
    setMaxQueue,
    setMinRating,
    setRadiusMeters
  } = useFilterStore()

  return (
    <aside className="memory-sidebar workbench-insights-panel" aria-label="筛选偏好">
      <div className="memory-sidebar-heading">
        <span>
          <SlidersHorizontal size={17} />
          筛选偏好
        </span>
        <button onClick={reset} title="重置筛选" type="button">
          <RotateCcw size={16} />
        </button>
      </div>

      <div className="memory-sidebar-count">
        <strong>{resultCount}</strong>
        <span>个候选地点</span>
      </div>

      <label>
        <span>品类</span>
        <select onChange={event => setCategory(event.target.value)} value={category}>
          <option value="all">全部品类</option>
          {categories.map(item => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
      </label>

      <label className="range-field">
        <span>人均不超过 ¥{maxPrice}</span>
        <input max={360} min={20} onChange={event => setMaxPrice(Number(event.target.value))} step={10} type="range" value={maxPrice} />
      </label>

      <label className="range-field">
        <span>最低评分 {minRating.toFixed(1)}</span>
        <input max={5} min={3.5} onChange={event => setMinRating(Number(event.target.value))} step={0.1} type="range" value={minRating} />
      </label>

      <label className="range-field">
        <span>排队不超过 {maxQueue} 分</span>
        <input max={90} min={0} onChange={event => setMaxQueue(Number(event.target.value))} step={5} type="range" value={maxQueue} />
      </label>

      <label className="range-field">
        <span>地理范围 {Math.round(radiusMeters / 1000)} km</span>
        <input
          max={16000}
          min={1000}
          onChange={event => setRadiusMeters(Number(event.target.value))}
          step={500}
          type="range"
          value={radiusMeters}
        />
      </label>
    </aside>
  )
}

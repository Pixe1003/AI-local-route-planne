import type { PoolResponse } from "../types/pool"
import { PoiCard } from "./PoiCard"

interface PoolGridProps {
  pool: PoolResponse
  selectedIds: Set<string>
  onSelectionChange: (ids: Set<string>) => void
}

export function PoolGrid({ pool, selectedIds, onSelectionChange }: PoolGridProps) {
  const toggle = (poiId: string) => {
    const next = new Set(selectedIds)
    if (next.has(poiId)) {
      next.delete(poiId)
    } else {
      next.add(poiId)
    }
    onSelectionChange(next)
  }

  const selectedCategories = pool.categories
    .flatMap(category => category.pois)
    .filter(poi => selectedIds.has(poi.id))
    .map(poi => poi.category)

  const reminder = selectedCategories.includes("restaurant")
    ? "已覆盖正餐点"
    : "还没有正餐点，建议加一家餐厅"

  return (
    <div className="pool-stack">
      <div className="selection-bar">
        <strong>已选 {selectedIds.size} 个 POI</strong>
        <span>{reminder}</span>
      </div>
      {pool.categories.map(category => (
        <section className="pool-section" key={category.name}>
          <div className="section-heading">
            <h2>{category.name}</h2>
            <p>{category.description}</p>
          </div>
          <div className="poi-grid">
            {category.pois.map(poi => (
              <PoiCard
                key={poi.id}
                onToggle={toggle}
                poi={poi}
                selected={selectedIds.has(poi.id)}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}

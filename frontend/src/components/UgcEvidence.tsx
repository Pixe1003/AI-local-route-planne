import type { UgcSnippet } from "../types/plan"

export function UgcEvidence({ items }: { items: UgcSnippet[] }) {
  return (
    <div className="ugc-list">
      {items.map(item => (
        <p key={`${item.source}-${item.quote}`}>“{item.quote}” · {item.source}</p>
      ))}
    </div>
  )
}

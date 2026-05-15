import { Brain, MapPin, ReceiptText, Users } from "lucide-react"
import { useEffect, useState } from "react"

import { fetchUserFacts } from "../api/agent"
import type { UserFacts } from "../types/userMemory"

export function UserMemoryPanel({ userId }: { userId: string }) {
  const [facts, setFacts] = useState<UserFacts | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchUserFacts(userId)
      .then(nextFacts => {
        if (!cancelled) setFacts(nextFacts)
      })
      .catch(() => {
        if (!cancelled) setFacts(null)
      })
    return () => {
      cancelled = true
    }
  }, [userId])

  if (!facts || facts.session_count === 0) return null

  return (
    <section className="user-memory-panel" aria-label="Agent memory">
      <div className="user-memory-title">
        <Brain size={17} />
        <strong>Agent 已记住偏好</strong>
      </div>
      <div className="user-memory-facts">
        {facts.typical_budget_range ? (
          <span>
            <ReceiptText size={14} />
            ¥{facts.typical_budget_range[0]}-{facts.typical_budget_range[1]}
          </span>
        ) : null}
        {facts.typical_party_type ? (
          <span>
            <Users size={14} />
            {facts.typical_party_type}
          </span>
        ) : null}
        {facts.favorite_districts.length ? (
          <span>
            <MapPin size={14} />
            {facts.favorite_districts.slice(0, 2).join(" / ")}
          </span>
        ) : null}
        {facts.favorite_categories.length ? (
          <span>{facts.favorite_categories.slice(0, 3).join(" / ")}</span>
        ) : null}
        {facts.avoid_categories.length ? (
          <span>避开 {facts.avoid_categories.slice(0, 2).join(" / ")}</span>
        ) : null}
      </div>
      <small>
        <span>{facts.session_count} 次会话</span>
        {facts.rejected_poi_ids.length ? <span> · 已避开 {facts.rejected_poi_ids.length} 个 POI</span> : null}
      </small>
    </section>
  )
}

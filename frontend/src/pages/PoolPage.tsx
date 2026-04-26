import { ArrowLeft, Route } from "lucide-react"
import { useNavigate } from "react-router-dom"

import { PoolGrid } from "../components/PoolGrid"
import { usePlanStore } from "../store/planStore"
import { usePoolStore } from "../store/poolStore"

export function PoolPage() {
  const navigate = useNavigate()
  const { pool, selectedIds, loading, error } = usePoolStore()
  const { generatePlans, loading: planLoading } = usePlanStore()

  if (!pool) {
    return (
      <main className="workspace empty-state">
        <h1>还没有推荐池</h1>
        <button className="secondary-button" onClick={() => navigate("/")} type="button">
          <ArrowLeft size={18} /> 返回输入
        </button>
      </main>
    )
  }

  const submit = async () => {
    await generatePlans({
      pool_id: pool.pool_id,
      selected_poi_ids: Array.from(selectedIds),
      free_text: "希望适合情侣拍照，晚上吃饭",
      context: {
        city: "shanghai",
        date: "2026-05-02",
        time_window: { start: "13:00", end: "21:00" },
        party: "couple",
        budget_per_person: 300
      }
    })
    navigate("/plan")
  }

  return (
    <main className="workspace">
      <div className="topbar">
        <button className="icon-button" onClick={() => navigate("/")} title="返回" type="button">
          <ArrowLeft size={18} />
        </button>
        <div>
          <h1>推荐池</h1>
          <p>{pool.meta.user_persona_summary}</p>
        </div>
        <button
          className="primary-button compact mobile-action-bar"
          disabled={loading || planLoading || selectedIds.size < 3}
          onClick={submit}
          type="button"
        >
          <Route size={18} />
          {planLoading ? "生成中" : "生成方案"}
        </button>
      </div>
      {error ? <p className="error-text">{error}</p> : null}
      <PoolGrid
        onSelectionChange={ids => usePoolStore.setState({ selectedIds: ids })}
        pool={pool}
        selectedIds={selectedIds}
      />
    </main>
  )
}

import { ArrowLeft, GitBranch, MapPinned, MessageSquareText } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"

import { PlanTimeline } from "../components/PlanTimeline"
import { usePlanStore } from "../store/planStore"
import { useTripStore } from "../store/tripStore"
import { versionSourceLabel } from "../utils/planning"

export function TripDetailPage() {
  const navigate = useNavigate()
  const { tripId } = useParams()
  const { currentTrip, fetchTrip, loading, error } = useTripStore()
  const { setPlansFromVersion } = usePlanStore()
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null)

  useEffect(() => {
    if (!tripId) return
    fetchTrip(tripId).then(trip => setSelectedVersionId(trip?.active_version_id ?? null))
  }, [fetchTrip, tripId])

  useEffect(() => {
    if (currentTrip && !selectedVersionId) setSelectedVersionId(currentTrip.active_version_id)
  }, [currentTrip, selectedVersionId])

  const selectedVersion = useMemo(
    () =>
      currentTrip?.versions.find(version => version.version_id === selectedVersionId) ??
      currentTrip?.versions.find(version => version.version_id === currentTrip.active_version_id),
    [currentTrip, selectedVersionId]
  )

  const activePlan = useMemo(
    () =>
      selectedVersion?.plans.find(plan => plan.plan_id === selectedVersion.active_plan_id) ??
      selectedVersion?.plans[0],
    [selectedVersion]
  )

  const continueAdjusting = () => {
    if (!tripId || !selectedVersion) return
    setPlansFromVersion(selectedVersion.plans, selectedVersion.active_plan_id)
    navigate(`/trips/${tripId}/plan`)
  }

  if (!currentTrip || !activePlan) {
    return (
      <main className="workspace empty-state">
        <h1>{loading ? "正在读取行程" : "没有找到行程"}</h1>
        {error ? <p className="error-text">{error}</p> : null}
        <button className="secondary-button" onClick={() => navigate("/")} type="button">
          <ArrowLeft size={18} /> 返回首页
        </button>
      </main>
    )
  }

  return (
    <main className="workspace trip-detail">
      <div className="topbar">
        <button className="icon-button" onClick={() => navigate("/")} title="返回首页" type="button">
          <ArrowLeft size={18} />
        </button>
        <div>
          <h1>{currentTrip.summary.title}</h1>
          <p>{currentTrip.summary.cover_poi_names.join(" / ")}</p>
        </div>
        <button className="primary-button compact" onClick={continueAdjusting} type="button">
          <MessageSquareText size={18} />
          继续调整
        </button>
      </div>

      <section className="insight-band">
        <div>
          <strong>{activePlan.summary.total_duration_min} 分钟</strong>
          <span>总时长</span>
        </div>
        <div>
          <strong>¥{activePlan.summary.total_cost}</strong>
          <span>估算花费</span>
        </div>
        <div>
          <strong>{currentTrip.versions.length}</strong>
          <span>版本数</span>
        </div>
        <div>
          <strong>{activePlan.summary.validation.is_valid ? "已通过" : "需修复"}</strong>
          <span>路线校验</span>
        </div>
      </section>

      <section className="trip-detail-layout">
        <div className="timeline">
          <div className="map-toolbar">
            <MapPinned size={18} />
            当前路线时间线
          </div>
          <PlanTimeline onStopClick={() => undefined} plan={activePlan} />
        </div>
        <aside className="version-panel">
          <div className="section-heading">
            <h2>版本历史</h2>
            <p>每次路线生成或对话调整都会保存为 RouteVersion。</p>
          </div>
          <div className="version-list">
            {[...currentTrip.versions].reverse().map(version => (
              <button
                className={version.version_id === selectedVersion?.version_id ? "version-item active" : "version-item"}
                key={version.version_id}
                onClick={() => setSelectedVersionId(version.version_id)}
                type="button"
              >
                <GitBranch size={16} />
                <span>{versionSourceLabel(version.source)}</span>
                <small>{new Date(version.created_at).toLocaleString()}</small>
                {version.user_message ? <em>{version.user_message}</em> : null}
              </button>
            ))}
          </div>
        </aside>
      </section>
    </main>
  )
}

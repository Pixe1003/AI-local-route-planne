import { ArrowLeft, RefreshCw, Send, Save } from "lucide-react"
import { FormEvent, useEffect, useMemo, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"

import { PlanCompare } from "../components/PlanCompare"
import { PlanMap } from "../components/PlanMap"
import { PlanTimeline } from "../components/PlanTimeline"
import { usePlanStore } from "../store/planStore"
import { useTripStore } from "../store/tripStore"
import type { AlternativePoi } from "../types/plan"

const replanShortcuts = ["少排队", "更省钱", "少走路", "雨天方案", "亲子友好", "老人友好", "压缩到 2 小时"]

export function PlanResultPage() {
  const navigate = useNavigate()
  const { tripId } = useParams()
  const {
    plans,
    activePlanId,
    switchPlan,
    sendAdjustment,
    replaceWithAlternative,
    setPlansFromVersion,
    loading,
    chatHistory
  } = usePlanStore()
  const { currentTrip, fetchTrip, saveVersion, loading: tripLoading, error: tripError } = useTripStore()
  const [highlighted, setHighlighted] = useState(0)
  const [message, setMessage] = useState("把第二站换成不需要排队的")

  useEffect(() => {
    if (!tripId) return
    if (currentTrip?.trip_id === tripId) return
    fetchTrip(tripId).then(trip => {
      const version = trip?.versions.find(item => item.version_id === trip.active_version_id)
      if (version) setPlansFromVersion(version.plans, version.active_plan_id)
    })
  }, [currentTrip?.trip_id, fetchTrip, setPlansFromVersion, tripId])

  useEffect(() => {
    const version = currentTrip?.versions.find(item => item.version_id === currentTrip.active_version_id)
    if (version && plans.length === 0) setPlansFromVersion(version.plans, version.active_plan_id)
  }, [currentTrip, plans.length, setPlansFromVersion])

  const activePlan = useMemo(
    () => plans.find(plan => plan.plan_id === activePlanId) ?? plans[0],
    [activePlanId, plans]
  )

  if (!activePlan) {
    return (
      <main className="workspace empty-state">
        <h1>还没有路线方案</h1>
        <button className="secondary-button" onClick={() => navigate("/trips/new/pool")} type="button">
          <ArrowLeft size={18} /> 返回推荐池
        </button>
      </main>
    )
  }

  const persistAdjustment = async (content: string) => {
    if (!content.trim() || !currentTrip) return
    const response = await sendAdjustment(content)
    if (!response?.updated_plan) return
    const latest = usePlanStore.getState()
    await saveVersion({
      trip_id: currentTrip.trip_id,
      user_id: currentTrip.user_id,
      profile: currentTrip.profile,
      planning_context: currentTrip.planning_context,
      plans: latest.plans,
      active_plan_id: latest.activePlanId ?? response.updated_plan.plan_id,
      pool_id: currentTrip.versions.at(-1)?.pool_id,
      selected_poi_ids: latest.plans[0]?.stops.map(stop => stop.poi_id) ?? [],
      source: "chat_adjustment",
      user_message: content
    })
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!message.trim()) return
    await persistAdjustment(message)
    setMessage("")
  }

  const replaceCandidate = async (candidate: AlternativePoi) => {
    const response = await replaceWithAlternative(candidate)
    if (!response?.updated_plan || !currentTrip) return
    const latest = usePlanStore.getState()
    await saveVersion({
      trip_id: currentTrip.trip_id,
      user_id: currentTrip.user_id,
      profile: currentTrip.profile,
      planning_context: currentTrip.planning_context,
      plans: latest.plans,
      active_plan_id: latest.activePlanId ?? response.updated_plan.plan_id,
      pool_id: currentTrip.versions.at(-1)?.pool_id,
      selected_poi_ids: latest.plans[0]?.stops.map(stop => stop.poi_id) ?? [],
      source: "alternative_replace",
      user_message: `替换为 ${candidate.poi_name}`
    })
  }

  return (
    <main className="workspace plan-workspace">
      <div className="topbar">
        <button
          className="icon-button"
          onClick={() => navigate(tripId ? `/trips/${tripId}` : "/trips/new/pool")}
          title="返回"
          type="button"
        >
          <ArrowLeft size={18} />
        </button>
        <div>
          <h1>{activePlan.title}</h1>
          <p>{activePlan.description}</p>
        </div>
        {tripId ? (
          <button className="secondary-button compact" onClick={() => navigate(`/trips/${tripId}`)} type="button">
            <Save size={18} />
            行程详情
          </button>
        ) : null}
      </div>
      {tripError ? <p className="error-text">{tripError}</p> : null}
      <PlanCompare activePlanId={activePlan.plan_id} onSwitch={switchPlan} plans={plans} />
      <section className="plan-layout">
        <PlanMap highlightedStopIndex={highlighted} onStopClick={setHighlighted} plan={activePlan} />
        <PlanTimeline onStopClick={setHighlighted} plan={activePlan} />
      </section>
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
          <strong>{activePlan.summary.total_queue_min} 分钟</strong>
          <span>排队风险</span>
        </div>
        <div>
          <strong>{activePlan.summary.validation.is_valid ? "已通过" : "需修复"}</strong>
          <span>约束校验</span>
        </div>
      </section>
      {(activePlan.alternative_pois ?? []).length ? (
        <section className="alternatives-panel">
          <div className="section-heading">
            <h2>可替换 POI</h2>
            <p>这些点没有强塞进主路线，适合按现场排队、预算或心情随时替换。</p>
          </div>
          <div className="alternative-grid">
            {(activePlan.alternative_pois ?? []).slice(0, 6).map(candidate => (
              <article className="alternative-card" key={candidate.poi_id}>
                <div>
                  <strong>{candidate.poi_name}</strong>
                  <span>{candidate.category} · 排队 {candidate.estimated_queue_min ?? "--"} 分 · ¥{candidate.estimated_cost ?? "--"}</span>
                </div>
                <p>{candidate.why_candidate}</p>
                <small>
                  {candidate.delta_minutes >= 0 ? "+" : ""}
                  {candidate.delta_minutes} 分钟 · 匹配 {Math.round(candidate.score_breakdown.total ?? 0)}
                </small>
                <button
                  className="secondary-button"
                  disabled={loading || tripLoading}
                  onClick={() => replaceCandidate(candidate)}
                  type="button"
                >
                  <RefreshCw size={16} />
                  替换第 {(candidate.replace_stop_index ?? 0) + 1} 站
                </button>
              </article>
            ))}
          </div>
        </section>
      ) : null}
      <section className="replan-panel">
        {replanShortcuts.map(shortcut => (
          <button
            className="secondary-button"
            disabled={loading || tripLoading}
            key={shortcut}
            onClick={() => persistAdjustment(shortcut)}
            type="button"
          >
            {shortcut}
          </button>
        ))}
      </section>
      <form className="chat-box" onSubmit={submit}>
        <div className="chat-history">
          {chatHistory.slice(-3).map(turn => (
            <p className={turn.role} key={`${turn.timestamp}-${turn.content}`}>
              {turn.content}
            </p>
          ))}
        </div>
        <div className="chat-input-row">
          <input aria-label="调整路线需求" onChange={event => setMessage(event.target.value)} value={message} />
          <button className="icon-button filled" disabled={loading || tripLoading} title="调整并保存版本" type="submit">
            <Send size={18} />
          </button>
        </div>
      </form>
    </main>
  )
}

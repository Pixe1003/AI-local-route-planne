import { ArrowLeft, Clock3, MapPin, Route } from "lucide-react"
import { FormEvent, useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"

import { adjustAgentRoute } from "../api/agent"
import { adjustRouteRecommendation } from "../api/chat"
import { createRouteChain } from "../api/route"
import { AgentThinkingPanel } from "../components/AgentThinkingPanel"
import { AmapRouteMap } from "../components/AmapRouteMap"
import { useAmapRouteStore } from "../store/amapRouteStore"
import type { RouteChainResponse } from "../types/route"

export function AmapRoutePage() {
  const navigate = useNavigate()
  const routeRequest = useAmapRouteStore(state => state.routeRequest)
  const setRouteRequest = useAmapRouteStore(state => state.setRouteRequest)
  const [routeResult, setRouteResult] = useState<RouteChainResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [feedback, setFeedback] = useState("")
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null)
  const [feedbackLoading, setFeedbackLoading] = useState(false)

  useEffect(() => {
    if (!routeRequest || routeRequest.poi_ids.length < 2) return

    if (
      routeRequest.route_chain &&
      routeChainMatchesRequest(routeRequest.route_chain, routeRequest.poi_ids, routeRequest.mode)
    ) {
      setRouteResult(routeRequest.route_chain)
      setLoading(false)
      setError(null)
      return
    }

    let cancelled = false
    setLoading(true)
    setError(null)
    createRouteChain({
      mode: routeRequest.mode,
      poi_ids: routeRequest.poi_ids
    })
      .then(result => {
        if (cancelled) return
        setRouteResult(result)
      })
      .catch(routeError => {
        if (cancelled) return
        setRouteResult(null)
        setError(routeError instanceof Error ? routeError.message : "高德路线生成失败")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [routeRequest])

  const storyPlan = routeRequest?.story_plan ?? null
  const storyByPoiId = useMemo(
    () => new Map((storyPlan?.stops ?? []).map(stop => [stop.poi_id, stop])),
    [storyPlan]
  )
  const orderedPois = routeResult?.ordered_pois ?? []
  const totalDistance = routeResult ? formatDistance(routeResult.total_distance_m) : "--"
  const totalDuration = routeResult ? formatDuration(routeResult.total_duration_s) : "--"
  const pageTitle = useMemo(() => {
    if (storyPlan?.theme) return storyPlan.theme
    if (!routeResult?.ordered_pois.length) return "高德路线规划"
    return routeResult.ordered_pois.map(poi => poi.name).slice(0, 3).join(" → ")
  }, [routeResult, storyPlan])

  const submitFeedback = async (event: FormEvent) => {
    event.preventDefault()
    if (!routeRequest || !feedback.trim()) return
    setFeedbackLoading(true)
    setError(null)
    try {
      if (routeRequest.session_id) {
        const response = await adjustAgentRoute({
          parent_session_id: routeRequest.session_id,
          user_message: feedback.trim()
        })
        const nextPoiIds = response.ordered_poi_ids.length
          ? response.ordered_poi_ids
          : response.pool?.default_selected_ids ?? []
        if (nextPoiIds.length >= 2) {
          setRouteRequest({
            ...routeRequest,
            poi_ids: nextPoiIds,
            session_id: response.session_id,
            route_chain: response.route_chain ?? null,
            story_plan: response.story_plan ?? routeRequest.story_plan ?? null,
            agent_steps: response.steps,
            free_text: routeRequest.free_text
              ? `${routeRequest.free_text}；${feedback.trim()}`
              : feedback.trim()
          })
        }
        setFeedbackMessage("已由 Agent 根据反馈更新路线")
        setFeedback("")
        return
      }
      const response = await adjustRouteRecommendation({
        pool_id: routeRequest.pool_id,
        current_poi_ids: routeRequest.poi_ids,
        user_message: feedback.trim(),
        chat_history: [],
        city: "hefei",
        date: routeRequest.date,
        time_window: routeRequest.time_window ?? null,
        free_text: routeRequest.free_text
      })
      const nextPoiIds = response.recommended_poi_ids ?? []
      if (nextPoiIds.length >= 2) {
        setRouteRequest({
          ...routeRequest,
          poi_ids: nextPoiIds,
          route_chain: null,
          free_text: routeRequest.free_text
            ? `${routeRequest.free_text}；${feedback.trim()}`
            : feedback.trim()
        })
      }
      setFeedbackMessage(response.assistant_message)
      setFeedback("")
    } catch (feedbackError) {
      setError(feedbackError instanceof Error ? feedbackError.message : "推荐更新失败")
    } finally {
      setFeedbackLoading(false)
    }
  }

  if (!routeRequest) {
    return (
      <main className="workspace empty-state">
        <div>
          <h1>还没有高德路线请求</h1>
          <p>先回到 UGC 首页选择偏好，再生成真实路线。</p>
        </div>
        <button className="primary-button" onClick={() => navigate("/")} type="button">
          <ArrowLeft size={18} />
          返回 UGC
        </button>
      </main>
    )
  }

  return (
    <main className="amap-route-page">
      <section className="amap-route-map-area">
        <AmapRouteMap geojson={routeResult?.geojson ?? null} pois={orderedPois} />
      </section>
      <aside className="amap-route-panel" aria-label="高德路线结果">
        <button className="secondary-button compact" onClick={() => navigate("/")} type="button">
          <ArrowLeft size={16} />
          UGC
        </button>
        <div className="amap-route-heading">
          <span className="eyebrow">高德真实路线</span>
          <h1>{pageTitle}</h1>
          <p>{storyPlan?.narrative ?? routeRequest.free_text ?? "基于 UGC 偏好和推荐池 POI 生成路线。"}</p>
        </div>

        <div className="route-summary-grid">
          <span>
            <strong>{totalDistance}</strong>
            总距离
          </span>
          <span>
            <strong>{totalDuration}</strong>
            预计耗时
          </span>
          <span>
            <strong>{routeRequest.poi_ids.length}</strong>
            POI
          </span>
          <span>
            <strong>{routeRequest.mode}</strong>
            模式
          </span>
        </div>

        {loading ? (
          <div className="route-panel-alert" role="status">
            <Route size={18} />
            正在请求高德路线
          </div>
        ) : null}
        {error ? <p className="route-panel-alert error">{error}</p> : null}

        <AgentThinkingPanel steps={routeRequest.agent_steps ?? []} />

        <form className="route-feedback-form" data-testid="route-feedback-form" onSubmit={submitFeedback}>
          <label>
            <span>调整推荐</span>
            <textarea
              aria-label="调整推荐"
              onChange={event => setFeedback(event.target.value)}
              placeholder="例如：少排队一点，不要商场，多一点本地菜"
              value={feedback}
            />
          </label>
          <button className="secondary-button compact" disabled={feedbackLoading || !feedback.trim()} type="submit">
            {feedbackLoading ? "更新中" : "更新 POI"}
          </button>
          {feedbackMessage ? <p>{feedbackMessage}</p> : null}
        </form>

        {orderedPois.length ? (
          <section className="route-poi-section">
            <h2>路线点位</h2>
            <ol className="route-poi-list">
              {orderedPois.map((poi, index) => (
                <li key={poi.id}>
                  <span className="poi-order">{index + 1}</span>
                  <div>
                    <strong>{poi.name}</strong>
                    <small>
                      <MapPin size={13} />
                      {poi.category ?? "POI"}
                    </small>
                    {storyByPoiId.get(poi.id) ? (
                      <div className="route-story-evidence">
                        <p>{storyByPoiId.get(poi.id)?.why}</p>
                        <blockquote>{storyByPoiId.get(poi.id)?.ugc_quote}</blockquote>
                      </div>
                    ) : null}
                  </div>
                </li>
              ))}
            </ol>
          </section>
        ) : null}

        {routeResult ? (
          <section className="route-poi-section">
            <h2>高德分段</h2>
            <ol className="route-segment-list">
              {routeResult.segments.map(segment => (
                <li key={segment.segment_index}>
                  <strong>
                    {segment.from_poi_name} → {segment.to_poi_name}
                  </strong>
                  <span>
                    <Clock3 size={13} />
                    {formatDuration(segment.duration_s)} · {formatDistance(segment.distance_m)}
                  </span>
                </li>
              ))}
            </ol>
          </section>
        ) : null}
      </aside>
    </main>
  )
}

function formatDistance(distanceM: number) {
  if (distanceM >= 1000) return `${(distanceM / 1000).toFixed(1)} km`
  return `${Math.round(distanceM)} m`
}

function formatDuration(durationS: number) {
  const minutes = Math.round(durationS / 60)
  if (minutes < 60) return `${minutes} 分钟`
  const hours = Math.floor(minutes / 60)
  const restMinutes = minutes % 60
  return restMinutes ? `${hours} 小时 ${restMinutes} 分钟` : `${hours} 小时`
}

function routeChainMatchesRequest(routeChain: RouteChainResponse, poiIds: string[], mode: string) {
  if (routeChain.mode !== mode) return false
  const routePoiIds = routeChain.ordered_pois.map(poi => poi.id)
  return routePoiIds.length === poiIds.length && routePoiIds.every((poiId, index) => poiId === poiIds[index])
}

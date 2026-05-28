import { ArrowLeft, Clock3, MapPin, Route } from "lucide-react"
import { FormEvent, useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"

import { adjustAgentRoute } from "../api/agent"
import { adjustRouteRecommendation } from "../api/chat"
import { createRouteChain } from "../api/route"
import { AgentThinkingPanel } from "../components/AgentThinkingPanel"
import { AmapRouteMap } from "../components/AmapRouteMap"
import { useAmapRouteStore } from "../store/amapRouteStore"
import type { RouteVariant } from "../types/agent"
import type { PoiInPool } from "../types/pool"
import type { AmapRouteRequest, RouteChainResponse, RoutePoi } from "../types/route"

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

  const robustness = routeRequest?.robustness ?? null
  const routeVariants = routeRequest?.route_variants ?? []
  const [selectedVariantIndex, setSelectedVariantIndex] = useState(0)
  useEffect(() => {
    setSelectedVariantIndex(0)
  }, [routeVariants])
  const activeVariantIndex = routeVariants.length
    ? Math.min(selectedVariantIndex, routeVariants.length - 1)
    : -1
  const activeVariant = activeVariantIndex >= 0 ? routeVariants[activeVariantIndex] : null
  const storyPlan = routeRequest?.story_plan ?? null
  const storyByPoiId = useMemo(
    () => new Map((storyPlan?.stops ?? []).map(stop => [stop.poi_id, stop])),
    [storyPlan]
  )
  const poolPoiById = useMemo(() => {
    const entries = (routeRequest?.pool?.categories ?? []).flatMap(category =>
      category.pois.map(poi => [poi.id, poi] as const)
    )
    return new Map(entries)
  }, [routeRequest?.pool])
  const orderedPois = routeResult?.ordered_pois ?? routePoisFromRequest(routeRequest, poolPoiById)
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
            route_variants: response.route_variants ?? routeRequest.route_variants ?? [],
            robustness: response.robustness ?? routeRequest.robustness ?? null,
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
        <AmapRouteMap geojson={routeResult?.geojson ?? null} mode={routeRequest.mode} pois={orderedPois} />
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

        {robustness ? (
          <div
            aria-label="路线鲁棒性"
            className="route-robustness-badge"
            data-testid="route-robustness-badge"
          >
            <span className="robustness-pill">
              准时概率 <strong>{Math.round(robustness.on_time_prob * 100)}%</strong>
            </span>
            <span className="robustness-meta">
              P90 总时长 {formatDuration(robustness.p90_total_min * 60)} · 期望超时 {Math.round(robustness.expected_overflow_min)} 分
              <small>· 蒙特卡洛 {robustness.samples} 次模拟</small>
            </span>
          </div>
        ) : null}

        {loading ? (
          <div className="route-panel-alert" role="status">
            <Route size={18} />
            正在请求高德路线
          </div>
        ) : null}
        {error ? <p className="route-panel-alert error">{error}</p> : null}
        {routeRequest.pool?.meta.data_warning ? (
          <p className="route-panel-alert">{routeRequest.pool.meta.data_warning}</p>
        ) : null}

        <AgentThinkingPanel steps={routeRequest.agent_steps ?? []} />

        {routeVariants.length > 1 ? (
          <section
            aria-label="Pareto 候选方案"
            className="route-variants-panel"
            data-testid="route-variants-panel"
          >
            <h2>方案对比（Pareto 前沿）</h2>
            <p className="route-variants-hint">
              非支配解集合：每条方案在兴趣 / 时长 / 花费 / 排队上至少有一个维度比其它更优。
            </p>
            <ul className="route-variants-list">
              {routeVariants.map((variant, index) => {
                const isActive = activeVariantIndex === index
                const reference = activeVariant
                const diff = reference && reference !== variant
                  ? describeVariantDiff(variant, reference)
                  : "当前方案"
                return (
                  <li
                    aria-current={isActive ? "true" : undefined}
                    className={isActive ? "route-variant-card active" : "route-variant-card"}
                    key={`${variant.label}-${index}`}
                  >
                    <button
                      className="route-variant-button"
                      onClick={() => setSelectedVariantIndex(index)}
                      type="button"
                    >
                      <header>
                        <strong>{variantLabel(variant.label)}</strong>
                        <small>{variant.solver}</small>
                      </header>
                      <div className="route-variant-metrics">
                        <span>兴趣 {variant.interest.toFixed(1)}</span>
                        <span>时长 {variant.time_min} 分</span>
                        <span>花费 ¥{variant.cost}</span>
                        <span>排队 {variant.queue_min} 分</span>
                      </div>
                      <p className="route-variant-diff">{diff}</p>
                    </button>
                  </li>
                )
              })}
            </ul>
          </section>
        ) : null}

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
              {orderedPois.map((poi, index) => {
                const poolPoi = poolPoiById.get(poi.id)
                const evidence = poolPoi?.evidence_snippets?.[0]
                return (
                  <li key={poi.id}>
                    <span className="poi-order">{index + 1}</span>
                    <div>
                      <strong>{poi.name}</strong>
                      <small>
                        <MapPin size={13} />
                        {poi.category ?? poolPoi?.category ?? "POI"}
                      </small>
                      {poolPoi?.distance_meters !== undefined && poolPoi.distance_meters !== null ? (
                        <small>距出发点 {formatDistance(poolPoi.distance_meters)}</small>
                      ) : null}
                      {poolPoi?.retrieval_provenance.length ? (
                        <div className="provenance-row">
                          {poolPoi.retrieval_provenance.map(item => (
                            <span key={item}>{item}</span>
                          ))}
                        </div>
                      ) : null}
                      {evidence ? (
                        <div className="route-retrieval-evidence">
                          <span>{evidence.source_type}</span>
                          <blockquote>{evidence.text}</blockquote>
                        </div>
                      ) : null}
                      {storyByPoiId.get(poi.id) ? (
                        <div className="route-story-evidence">
                          <p>{storyByPoiId.get(poi.id)?.why}</p>
                          <blockquote>{storyByPoiId.get(poi.id)?.ugc_quote}</blockquote>
                        </div>
                      ) : null}
                    </div>
                  </li>
                )
              })}
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

const VARIANT_LABELS: Record<string, string> = {
  interest: "兴趣最高",
  balanced: "折中",
  time_saving: "更省时",
  budget_saving: "更省钱",
  low_queue: "排队更少",
  frontier_interest: "前沿·兴趣",
  frontier_budget: "前沿·预算",
  frontier_queue: "前沿·排队",
  frontier: "前沿候选"
}

function variantLabel(label: string): string {
  return VARIANT_LABELS[label] ?? label
}

function describeVariantDiff(candidate: RouteVariant, reference: RouteVariant): string {
  const parts: string[] = []
  const interestDiff = candidate.interest - reference.interest
  const timeDiff = candidate.time_min - reference.time_min
  const costDiff = candidate.cost - reference.cost
  const queueDiff = candidate.queue_min - reference.queue_min

  if (Math.abs(interestDiff) >= 0.05) {
    parts.push(`${interestDiff > 0 ? "多" : "少"} ${Math.abs(interestDiff).toFixed(1)} 兴趣`)
  }
  if (Math.abs(timeDiff) >= 1) {
    parts.push(`${timeDiff > 0 ? "多" : "省"} ${Math.abs(timeDiff)} 分时长`)
  }
  if (Math.abs(costDiff) >= 1) {
    parts.push(`${costDiff > 0 ? "多" : "省"} ¥${Math.abs(costDiff)}`)
  }
  if (Math.abs(queueDiff) >= 1) {
    parts.push(`${queueDiff > 0 ? "多" : "少"} ${Math.abs(queueDiff)} 分排队`)
  }
  return parts.length ? `相比当前 ${parts.join("、")}` : "与当前几乎持平"
}

function routePoisFromRequest(
  routeRequest: AmapRouteRequest | null,
  poolPoiById: Map<string, PoiInPool>
): RoutePoi[] {
  if (!routeRequest) return []
  const routePois: RoutePoi[] = []
  routeRequest.poi_ids.forEach(poiId => {
    const poi = poolPoiById.get(poiId)
    if (!poi) return
    routePois.push({
      id: poi.id,
      name: poi.name,
      longitude: poi.longitude,
      latitude: poi.latitude,
      category: poi.category,
      cover_image: poi.cover_image ?? null
    })
  })
  return routePois
}

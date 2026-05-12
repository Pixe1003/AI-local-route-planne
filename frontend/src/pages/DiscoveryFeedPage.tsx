import { Clock3, Heart, MapPin, Route, Sparkles, Star, Trash2 } from "lucide-react"
import { FormEvent, useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"

import { runAgentRoute } from "../api/agent"
import { fetchUgcFeed } from "../api/ugc"
import { useAmapRouteStore } from "../store/amapRouteStore"
import { usePoolStore } from "../store/poolStore"
import { usePreferenceStore } from "../store/preferenceStore"
import { useUserStore } from "../store/userStore"
import type { UserNeedProfile } from "../types/onboarding"
import type { PreferenceSnapshot } from "../types/preferences"
import type { PoolRequest } from "../types/pool"
import type { UgcFeedItem } from "../types/ugc"

const categoryLabels: Record<string, string> = {
  restaurant: "餐饮",
  cafe: "咖啡",
  scenic: "景点",
  culture: "文化",
  shopping: "逛街",
  outdoor: "散步",
  entertainment: "娱乐",
  nightlife: "夜景"
}

export function DiscoveryFeedPage() {
  const navigate = useNavigate()
  const { userId, setNeedProfile } = useUserStore()
  const { likedPoiIds, isLiked, toggleLike, syncSnapshot, clearLikes, loading: preferenceLoading } = usePreferenceStore()
  const { fetchPool, loading: poolLoading, error: poolError } = usePoolStore()
  const { setRouteRequest } = useAmapRouteStore()
  const [feed, setFeed] = useState<UgcFeedItem[]>([])
  const [feedError, setFeedError] = useState<string | null>(null)
  const [panelOpen, setPanelOpen] = useState(false)
  const [query, setQuery] = useState("今天下午想少排队、吃本地菜、顺路拍照")
  const [date, setDate] = useState("2026-05-08")
  const [start, setStart] = useState("14:00")
  const [end, setEnd] = useState("20:00")
  const [budget, setBudget] = useState(180)
  const [agentLoading, setAgentLoading] = useState(false)

  useEffect(() => {
    fetchUgcFeed()
      .then(setFeed)
      .catch(error => setFeedError(error instanceof Error ? error.message : "UGC 内容加载失败"))
  }, [])

  const likedItems = useMemo(
    () => feed.filter(item => likedPoiIds.includes(item.poi_id)),
    [feed, likedPoiIds]
  )

  const busy = preferenceLoading || poolLoading || agentLoading

  const buildProfile = (): UserNeedProfile => ({
    user_id: userId,
    destination: {
      city: "hefei",
      start_location: "合肥市中心",
      target_area: "合肥核心城区",
      end_location: null
    },
    time: {
      start_time: start,
      end_time: end,
      time_budget_minutes: null
    },
    date,
    activity_preferences: query.includes("拍照") ? ["拍照", "打卡"] : [],
    food_preferences: query.includes("吃") || query.includes("本地菜") ? ["本地菜", "美食"] : [],
    taste_preferences: [],
    party_type: "friends",
    budget: { budget_per_person: budget, strict: false },
    route_style: [query.includes("少排队") ? "少排队" : "即时路线"],
    avoid: query.includes("少排队") ? ["长时间排队"] : [],
    must_visit: [],
    must_avoid: [],
    completeness_score: 1,
    raw_query: query
  })

  const poolRequest = (profile: UserNeedProfile, snapshot: PreferenceSnapshot): PoolRequest => ({
    user_id: userId,
    city: "hefei",
    date,
    time_window: { start, end },
    persona_tags: ["foodie", "photographer"],
    pace_style: "balanced",
    party: "friends",
    budget_per_person: budget,
    free_text: query,
    need_profile: profile,
    preference_snapshot: snapshot
  })

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const snapshot = await syncSnapshot(userId, "hefei")
    if (!snapshot) return
    const profile = buildProfile()
    setNeedProfile(profile)
    setAgentLoading(true)
    try {
      const agentResult = await runAgentRoute({
        user_id: userId,
        free_text: query,
        city: "hefei",
        date,
        time_window: { start, end },
        budget_per_person: budget,
        preference_snapshot: snapshot
      })
      const routePoiIds = agentResult.ordered_poi_ids.length
        ? agentResult.ordered_poi_ids
        : agentResult.pool?.default_selected_ids ?? []
      if (routePoiIds.length < 2) {
        setFeedError("至少需要 2 个 POI 才能生成高德路线")
        return
      }
      setRouteRequest({
        mode: agentResult.route_chain?.mode ?? "driving",
        poi_ids: routePoiIds,
        source: "ugc_instant_route",
        pool_id: agentResult.pool?.pool_id,
        session_id: agentResult.session_id,
        free_text: query,
        date,
        time_window: { start, end }
      })
      navigate("/route-map")
      return
    } catch (agentError) {
      setFeedError(agentError instanceof Error ? agentError.message : "Agent 路线生成失败，已切换稳定模式")
    } finally {
      setAgentLoading(false)
    }

    const pool = await fetchPool(poolRequest(profile, snapshot))
    if (!pool) return
    const routePoiIds = pool.default_selected_ids.slice(0, 5)
    if (routePoiIds.length < 2) {
      setFeedError("至少需要 2 个 POI 才能生成高德路线")
      return
    }
    setRouteRequest({
      mode: "driving",
      poi_ids: routePoiIds,
      source: "ugc_instant_route",
      pool_id: pool.pool_id,
      free_text: query,
      date,
      time_window: { start, end }
    })
    navigate("/route-map")
  }

  return (
    <main className="workspace discovery-workspace">
      <section className="discovery-header">
        <div>
          <span className="eyebrow">UGC 偏好冷启动</span>
          <h1>现在就出发</h1>
          <p>收藏会模拟历史偏好，路线会优先参考你喜欢过的标签、类别和 POI。</p>
        </div>
      </section>

      <section className="liked-strip">
        <div>
          <strong>已收藏 {likedPoiIds.length} 个</strong>
          <span>
            {likedItems.length
              ? likedItems.map(item => item.poi_name).slice(0, 4).join(" / ")
              : "先刷几张 UGC 卡片，也可以直接规划"}
          </span>
        </div>
        <button
          className="clear-likes-button"
          disabled={!likedPoiIds.length}
          onClick={clearLikes}
          title="清空收藏"
          type="button"
        >
          <Trash2 size={16} />
          清零
        </button>
      </section>

      {feedError ? <p className="error-text">{feedError}</p> : null}
      <section className="ugc-feed-grid">
        {feed.map(item => (
          <article className={isLiked(item.poi_id) ? "ugc-card liked" : "ugc-card"} key={item.post_id}>
            <div className="ugc-cover-wrap">
              <img alt={item.poi_name} className="ugc-cover" src={item.cover_image ?? ""} />
              <button
                className={isLiked(item.poi_id) ? "heart-button active" : "heart-button"}
                onClick={() => toggleLike(item)}
                title={isLiked(item.poi_id) ? "取消收藏" : "收藏"}
                type="button"
              >
                <Heart fill={isLiked(item.poi_id) ? "currentColor" : "none"} size={18} />
              </button>
            </div>
            <div className="ugc-body">
              <div className="ugc-title-row">
                <h2>{item.title}</h2>
                <span>{categoryLabels[item.category] ?? item.category}</span>
              </div>
              <strong>{item.poi_name}</strong>
              <p>{item.quote}</p>
              <div className="ugc-meta">
                <span>
                  <Star size={14} /> {item.rating.toFixed(1)}
                </span>
                <span>¥{item.price_per_person ?? "--"}</span>
                <span>
                  <Clock3 size={14} /> {item.estimated_queue_min ?? "--"} 分
                </span>
              </div>
              <div className="keyword-row">
                {item.tags.slice(0, 3).map(tag => (
                  <span key={tag}>{tag}</span>
                ))}
              </div>
              <small>
                <MapPin size={13} /> {item.source} · {item.author}
              </small>
            </div>
          </article>
        ))}
      </section>

      {panelOpen ? (
        <form className="instant-panel" onSubmit={submit}>
          <label>
            <span>这次想怎么走</span>
            <textarea onChange={event => setQuery(event.target.value)} value={query} />
          </label>
          <div className="form-row">
            <label>
              <span>日期</span>
              <input onChange={event => setDate(event.target.value)} type="date" value={date} />
            </label>
            <label>
              <span>预算/人</span>
              <input min={0} onChange={event => setBudget(Number(event.target.value))} type="number" value={budget} />
            </label>
          </div>
          <div className="form-row">
            <label>
              <span>开始</span>
              <input onChange={event => setStart(event.target.value)} type="time" value={start} />
            </label>
            <label>
              <span>结束</span>
              <input onChange={event => setEnd(event.target.value)} type="time" value={end} />
            </label>
          </div>
          {poolError ? <p className="error-text">{poolError}</p> : null}
          <button className="primary-button" disabled={busy} type="submit">
            <Route size={18} />
            {busy ? "生成中" : "生成即时路线"}
          </button>
        </form>
      ) : null}

      <div className="instant-cta">
        <button className="primary-button" onClick={() => setPanelOpen(true)} type="button">
          <Sparkles size={18} />
          已收藏 {likedPoiIds.length} 个 · 现在出发
        </button>
      </div>
    </main>
  )
}

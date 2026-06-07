import { ChevronLeft, ChevronRight, Clock3, Heart, MapPin, Search, Star } from "lucide-react"
import { FormEvent, useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"

import { runAgentRoute } from "../api/agent"
import { fetchSystemHealth, type SystemHealth } from "../api/health"
import { fetchUgcFeed } from "../api/ugc"
import { AmapRouteMap } from "../components/AmapRouteMap"
import { MemorySidebar } from "../components/MemorySidebar"
import { PlanBasket } from "../components/PlanBasket"
import { PlanningOverlay } from "../components/PlanningOverlay"
import { useAgentPlanningStore } from "../store/agentPlanningStore"
import { useAmapRouteStore } from "../store/amapRouteStore"
import { useFilterStore } from "../store/filterStore"
import { usePoolStore } from "../store/poolStore"
import { usePreferenceStore } from "../store/preferenceStore"
import { useUserStore } from "../store/userStore"
import type { UserNeedProfile } from "../types/onboarding"
import type { PreferenceSnapshot } from "../types/preferences"
import type { PoolRequest, WeatherCondition } from "../types/pool"
import type { RoutePoi } from "../types/route"
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

const categoryOptions = Object.entries(categoryLabels).map(([value, label]) => ({ value, label }))

const originOptions = [
  { id: "downtown", label: "合肥市中心", latitude: 31.8206, longitude: 117.2272 },
  { id: "south_station", label: "合肥南站", latitude: 31.7994, longitude: 117.2906 },
  { id: "xiaoyaojin", label: "逍遥津", latitude: 31.8682, longitude: 117.2952 }
]

const demoFeedFallback: UgcFeedItem[] = [
  {
    post_id: "demo_ugc_1",
    poi_id: "demo_poi_leijie",
    poi_name: "罍街",
    title: "下班后这条夜市线很稳",
    source: "demo_ugc",
    author: "合肥体验官",
    cover_image: null,
    quote: "先吃小吃再散步，排队不会太夸张。",
    tags: ["夜市", "本地菜", "朋友"],
    category: "restaurant",
    rating: 4.7,
    price_per_person: 76,
    estimated_queue_min: 14,
    city: "hefei"
  },
  {
    post_id: "demo_ugc_2",
    poi_id: "demo_poi_swanlake",
    poi_name: "天鹅湖",
    title: "傍晚拍照光线很舒服",
    source: "demo_ugc",
    author: "城市漫游者",
    cover_image: null,
    quote: "适合饭后散步，离政务区商圈也近。",
    tags: ["夜景", "散步", "拍照"],
    category: "outdoor",
    rating: 4.8,
    price_per_person: 0,
    estimated_queue_min: 0,
    city: "hefei"
  },
  {
    post_id: "demo_ugc_3",
    poi_id: "demo_poi_museum",
    poi_name: "安徽博物院",
    title: "雨天也能安排的文化点",
    source: "demo_ugc",
    author: "周末计划员",
    cover_image: null,
    quote: "室内动线清楚，和咖啡店组合起来不赶。",
    tags: ["文化", "室内", "雨天"],
    category: "culture",
    rating: 4.6,
    price_per_person: 0,
    estimated_queue_min: 8,
    city: "hefei"
  },
  {
    post_id: "demo_ugc_4",
    poi_id: "demo_poi_cafe",
    poi_name: "环城公园咖啡",
    title: "路线中段适合休息一下",
    source: "demo_ugc",
    author: "咖啡地图",
    cover_image: null,
    quote: "不想太累时，把它放在两个景点中间很合适。",
    tags: ["咖啡", "休息", "顺路"],
    category: "cafe",
    rating: 4.5,
    price_per_person: 42,
    estimated_queue_min: 10,
    city: "hefei"
  }
]

const weatherOptions: Array<{ value: WeatherCondition; label: string }> = [
  { value: "normal", label: "晴天/普通" },
  { value: "rainy", label: "雨天" },
  { value: "hot", label: "炎热" },
  { value: "cold", label: "偏冷" }
]

function todayIso() {
  const date = new Date()
  const offsetMs = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 10)
}

function hasCoordinates(item: UgcFeedItem): item is UgcFeedItem & { latitude: number; longitude: number } {
  return (
    typeof item.latitude === "number" &&
    typeof item.longitude === "number" &&
    Number.isFinite(item.latitude) &&
    Number.isFinite(item.longitude)
  )
}

export function DiscoveryFeedPage() {
  const navigate = useNavigate()
  const { userId, setNeedProfile } = useUserStore()
  const {
    likedItems: likedItemMap,
    likedPoiIds,
    isLiked,
    toggleLike,
    syncSnapshot,
    clearLikes,
    loading: preferenceLoading
  } = usePreferenceStore()
  const { fetchPool, loading: poolLoading, error: poolError } = usePoolStore()
  const { setRouteRequest } = useAmapRouteStore()
  const { category, maxPrice, maxQueue, minRating } = useFilterStore()
  const startPlanning = useAgentPlanningStore(state => state.start)
  const pushPlanningStep = useAgentPlanningStore(state => state.pushStep)
  const finishPlanning = useAgentPlanningStore(state => state.finish)
  const [feed, setFeed] = useState<UgcFeedItem[]>([])
  const [feedError, setFeedError] = useState<string | null>(null)
  const [listCollapsed, setListCollapsed] = useState(false)
  const [searchTerm, setSearchTerm] = useState("")
  const [highlightedPoiId, setHighlightedPoiId] = useState<string | null>(null)
  const [query, setQuery] = useState("今天下午想少排队、吃本地菜、顺路拍照")
  const [date, setDate] = useState(todayIso)
  const [start, setStart] = useState("14:00")
  const [end, setEnd] = useState("20:00")
  const [budget, setBudget] = useState(180)
  const [weatherCondition, setWeatherCondition] = useState<WeatherCondition>("normal")
  const [originId, setOriginId] = useState(originOptions[0].id)
  const [radiusMeters, setRadiusMeters] = useState(8000)
  const [systemHealth, setSystemHealth] = useState<SystemHealth | null>(null)
  const [agentLoading, setAgentLoading] = useState(false)

  useEffect(() => {
    fetchUgcFeed()
      .then(setFeed)
      .catch(() => {
        setFeed(demoFeedFallback)
        setFeedError("后端 UGC 暂不可用，已展示前端演示数据")
      })
  }, [])

  useEffect(() => {
    fetchSystemHealth()
      .then(setSystemHealth)
      .catch(() => setSystemHealth(null))
  }, [])

  const displayFeed = useMemo(() => {
    const uniqueItems = new Map<string, UgcFeedItem>()
    for (const item of feed) {
      if (!uniqueItems.has(item.poi_id)) {
        uniqueItems.set(item.poi_id, item)
      }
    }
    return Array.from(uniqueItems.values())
  }, [feed])

  const feedByPoiId = useMemo(
    () => new Map(displayFeed.map(item => [item.poi_id, item] as const)),
    [displayFeed]
  )

  const filteredFeed = useMemo(() => {
    const term = searchTerm.trim().toLowerCase()
    return displayFeed.filter(item => {
      const price = item.price_per_person ?? 0
      const queue = item.estimated_queue_min ?? 0
      const matchesCategory = category === "all" || item.category === category
      const matchesSearch =
        !term ||
        [item.poi_name, item.title, item.quote, item.author, ...item.tags].some(value =>
          value.toLowerCase().includes(term)
        )
      return (
        matchesCategory &&
        matchesSearch &&
        item.rating >= minRating &&
        price <= maxPrice &&
        queue <= maxQueue
      )
    })
  }, [category, displayFeed, maxPrice, maxQueue, minRating, searchTerm])

  const likedItems = useMemo(
    () =>
      likedPoiIds
        .map(poiId => likedItemMap[poiId] ?? feedByPoiId.get(poiId))
        .filter((item): item is UgcFeedItem => Boolean(item)),
    [feedByPoiId, likedItemMap, likedPoiIds]
  )

  const previewPois = useMemo<RoutePoi[]>(
    () =>
      filteredFeed
        .filter(hasCoordinates)
        .slice(0, 12)
        .map(item => ({
          id: item.poi_id,
          name: item.poi_name,
          category: item.category,
          longitude: item.longitude,
          latitude: item.latitude
        })),
    [filteredFeed]
  )

  const busy = preferenceLoading || poolLoading || agentLoading
  const origin = originOptions.find(item => item.id === originId) ?? originOptions[0]
  const originPayload = {
    origin_latitude: origin.latitude,
    origin_longitude: origin.longitude,
    radius_meters: radiusMeters
  }

  const buildProfile = (): UserNeedProfile => ({
    user_id: userId,
    destination: {
      city: "hefei",
      start_location: "合肥市中心",
      start_latitude: origin.latitude,
      start_longitude: origin.longitude,
      radius_meters: radiusMeters,
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
    weather_condition: weatherCondition,
    free_text: query,
    need_profile: profile,
    preference_snapshot: snapshot,
    ...originPayload
  })

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setFeedError(null)
    startPlanning()
    setAgentLoading(true)
    try {
      pushPlanningStep("同步收藏偏好")
      const snapshot = await syncSnapshot(userId, "hefei")
      if (!snapshot) return
      const profile = buildProfile()
      setNeedProfile(profile)
      try {
        pushPlanningStep("Agent 生成候选路线")
        const agentResult = await runAgentRoute({
          user_id: userId,
          free_text: query,
          city: "hefei",
          date,
          time_window: { start, end },
          budget_per_person: budget,
          weather_condition: weatherCondition,
          need_profile: profile,
          preference_snapshot: snapshot,
          ...originPayload
        })
        const routePoiIds = agentResult.ordered_poi_ids.length
          ? agentResult.ordered_poi_ids
          : agentResult.pool?.default_selected_ids ?? []
        if (routePoiIds.length < 2) {
          setFeedError("至少需要 2 个 POI 才能生成高德路线")
          return
        }
        pushPlanningStep("写入高德路线请求")
        setRouteRequest({
          mode: agentResult.route_chain?.mode ?? "driving",
          poi_ids: routePoiIds,
          source: "ugc_instant_route",
          pool_id: agentResult.pool?.pool_id,
          pool: agentResult.pool ?? null,
          session_id: agentResult.session_id,
          route_chain: agentResult.route_chain ?? null,
          story_plan: agentResult.story_plan ?? null,
          agent_steps: agentResult.steps,
          route_variants: agentResult.route_variants ?? [],
          robustness: agentResult.robustness ?? null,
          transport_notice: agentResult.transport_notice ?? null,
          weather_condition: weatherCondition,
          free_text: query,
          date,
          time_window: { start, end }
        })
        navigate("/route-map")
        return
      } catch (agentError) {
        setFeedError(agentError instanceof Error ? agentError.message : "Agent 路线生成失败，已切换稳定模式")
      }

      pushPlanningStep("切换稳定规划模式")
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
        pool,
        weather_condition: weatherCondition,
        free_text: query,
        date,
        time_window: { start, end }
      })
      navigate("/route-map")
    } finally {
      setAgentLoading(false)
      finishPlanning()
    }
  }

  return (
    <main className={listCollapsed ? "discovery-workspace discover-shell service-workbench list-collapsed" : "discovery-workspace discover-shell service-workbench"}>
      <section className="workbench-feed-panel discover-list-panel" aria-label="UGC 发现列表">
        <header className="discover-list-header">
          <div>
            <span className="eyebrow">合肥本地生活 Demo</span>
            <h1>AIroute 即时路线工作台</h1>
            <p>从 UGC 灵感、偏好记忆和真实地图里快速拼出一条能出发的路线。</p>
          </div>
          <button
            aria-expanded={!listCollapsed}
            className="collapse-list-button"
            onClick={() => setListCollapsed(value => !value)}
            title={listCollapsed ? "展开列表" : "收起列表"}
            type="button"
          >
            {listCollapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          </button>
        </header>

        {!listCollapsed ? (
          <>
            {systemHealth ? (
              <div className="system-status-row" aria-label="系统状态">
                <span>RAG {systemHealth.rag?.status ?? "unknown"}</span>
                <span>FAISS {systemHealth.faiss?.document_count ?? 0}</span>
                <span>高德 {systemHealth.amap?.status ?? "unknown"}</span>
              </div>
            ) : null}

            <label className="discover-search">
              <Search size={16} />
              <input
                aria-label="搜索 UGC 地点"
                onChange={event => setSearchTerm(event.target.value)}
                placeholder="搜索地点、标签或作者"
                value={searchTerm}
              />
            </label>

            <section className="liked-strip discover-liked-summary">
              <div>
                <strong>已收藏 {likedPoiIds.length} 个</strong>
                <span>
                  {likedItems.length
                    ? likedItems.map(item => item.poi_name).slice(0, 4).join(" / ")
                    : "先刷几张 UGC 卡片，也可以直接规划"}
                </span>
              </div>
            </section>

            {feedError ? (
              <p className={feedError.includes("暂不可用") ? "demo-notice" : "error-text"}>{feedError}</p>
            ) : null}
            <section className="ugc-feed-grid discover-card-list">
              {filteredFeed.map(item => (
                <article
                  className={isLiked(item.poi_id) ? "ugc-card liked" : "ugc-card"}
                  key={item.post_id}
                  onMouseEnter={() => setHighlightedPoiId(item.poi_id)}
                >
                  <div className="ugc-cover-wrap">
                    {item.cover_image ? (
                      <img alt={item.poi_name} className="ugc-cover" src={item.cover_image} />
                    ) : (
                      <div aria-label={item.poi_name} className="ugc-cover ugc-cover-placeholder" role="img">
                        <MapPin size={22} />
                      </div>
                    )}
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
          </>
        ) : null}
      </section>

      <section className="workbench-map-panel route-preview-card discover-map-stage" aria-label="地图预览">
        <div className="map-stage-topbar">
          <div>
            <span>地图预览</span>
            <strong>{previewPois.length || "--"} 个候选点</strong>
          </div>
          <small>点击 marker 联动列表</small>
        </div>
        <AmapRouteMap
          geojson={null}
          highlightedPoiId={highlightedPoiId}
          onMarkerClick={setHighlightedPoiId}
          pois={previewPois}
          showAllMarkers
        />
      </section>

      <MemorySidebar categories={categoryOptions} resultCount={filteredFeed.length} />

      <section className="workbench-command-panel" aria-label="Agent 规划">
        <PlanBasket
          budget={budget}
          busy={busy}
          date={date}
          end={end}
          error={poolError}
          likedItems={likedItems}
          likedPoiCount={likedPoiIds.length}
          onClearLikes={clearLikes}
          onSubmit={submit}
          originId={originId}
          originOptions={originOptions}
          query={query}
          radiusMeters={radiusMeters}
          setBudget={setBudget}
          setDate={setDate}
          setEnd={setEnd}
          setOriginId={setOriginId}
          setQuery={setQuery}
          setRadiusMeters={setRadiusMeters}
          setStart={setStart}
          setWeatherCondition={setWeatherCondition}
          start={start}
          weatherCondition={weatherCondition}
          weatherOptions={weatherOptions}
        />
        <section className="poi-table command-poi-table" aria-label="候选 POI">
          <header className="poi-table-header">
            <div>
              <span className="eyebrow">候选 POI</span>
              <h2>{filteredFeed.length} 个可规划地点</h2>
            </div>
            <small>按筛选与偏好实时更新</small>
          </header>
          <div className="poi-table-list">
            {filteredFeed.slice(0, 6).map((item, index) => (
              <button
                className={isLiked(item.poi_id) ? "poi-table-row liked" : "poi-table-row"}
                key={item.poi_id}
                onClick={() => setHighlightedPoiId(item.poi_id)}
                type="button"
              >
                <span className="poi-table-index">{index + 1}</span>
                <span className="poi-table-main">
                  <strong>{item.poi_name}</strong>
                  <small>{categoryLabels[item.category] ?? item.category} · {item.title}</small>
                </span>
                <span>{item.estimated_queue_min ?? "--"} 分钟</span>
                <span>¥{item.price_per_person ?? "--"}</span>
                <span>{item.rating.toFixed(1)}</span>
              </button>
            ))}
          </div>
        </section>
      </section>
      <PlanningOverlay />
    </main>
  )
}

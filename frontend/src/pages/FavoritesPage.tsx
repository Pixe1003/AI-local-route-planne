import { Heart, MapPin, ReceiptText, Star, Trash2, Users } from "lucide-react"
import { useMemo, useState } from "react"

import { UserMemoryPanel } from "../components/UserMemoryPanel"
import { usePreferenceStore } from "../store/preferenceStore"
import { useUserStore } from "../store/userStore"
import type { UgcFeedItem } from "../types/ugc"

export function FavoritesPage() {
  const { userId } = useUserStore()
  const { clearLikes, likedItems, likedPoiIds, toggleLike } = usePreferenceStore()
  const [budgetText, setBudgetText] = useState("80-180")
  const [travelMode, setTravelMode] = useState("步行 + 打车")
  const [districtText, setDistrictText] = useState("包河 / 蜀山 / 政务区")
  const [categoryText, setCategoryText] = useState("本地菜 / 咖啡 / 夜景")

  const items = useMemo(
    () => likedPoiIds.map(poiId => likedItems[poiId]).filter((item): item is UgcFeedItem => Boolean(item)),
    [likedItems, likedPoiIds]
  )

  return (
    <main className="favorites-page favorites-service-shell">
      <section className="favorites-hero">
        <span className="eyebrow">收藏夹</span>
        <h1>把想去的地方先放进行程袋</h1>
        <p>收藏会沉淀成本地偏好，下一次 Agent 规划路线时优先考虑这些地点和口味。</p>
      </section>

      <section className="favorites-grid">
        <div className="favorites-list-panel">
          <div className="favorites-panel-heading">
            <div>
              <span>{items.length} 个地点</span>
              <h2>已收藏 POI</h2>
            </div>
            <button className="basket-clear-button" disabled={!items.length} onClick={clearLikes} type="button">
              <Trash2 size={15} />
              清空
            </button>
          </div>

          {items.length ? (
            <div className="favorite-card-list">
              {items.map(item => (
                <article className="favorite-card" key={item.poi_id}>
                  {item.cover_image ? (
                    <img alt={item.poi_name} src={item.cover_image} />
                  ) : (
                    <div className="favorite-card-placeholder" aria-label={item.poi_name} role="img">
                      <MapPin size={22} />
                    </div>
                  )}
                  <div>
                    <span>{item.category}</span>
                    <h3>{item.poi_name}</h3>
                    <p>{item.quote}</p>
                    <div className="favorite-card-meta">
                      <small>
                        <Star size={13} />
                        {item.rating.toFixed(1)}
                      </small>
                      <small>¥{item.price_per_person ?? "--"}</small>
                      <small>{item.estimated_queue_min ?? "--"} 分排队</small>
                    </div>
                  </div>
                  <button onClick={() => toggleLike(item)} title="取消收藏" type="button">
                    <Heart fill="currentColor" size={17} />
                  </button>
                </article>
              ))}
            </div>
          ) : (
            <div className="favorites-empty">
              <Heart size={26} />
              <strong>还没有收藏地点</strong>
              <span>回到规划页收藏几个 UGC 地点，这里会自动出现。</span>
            </div>
          )}
        </div>

        <aside className="favorites-memory-panel" aria-label="Agent 偏好记忆">
          <div className="favorites-panel-heading">
            <div>
              <span>可编辑</span>
              <h2>Agent 偏好记忆</h2>
            </div>
          </div>
          <UserMemoryPanel userId={userId} />
          <div className="memory-edit-grid">
            <label>
              <span>
                <ReceiptText size={14} />
                预算范围
              </span>
              <input onChange={event => setBudgetText(event.target.value)} value={budgetText} />
            </label>
            <label>
              <span>
                <Users size={14} />
                出行方式
              </span>
              <input onChange={event => setTravelMode(event.target.value)} value={travelMode} />
            </label>
            <label>
              <span>常去区域</span>
              <textarea onChange={event => setDistrictText(event.target.value)} value={districtText} />
            </label>
            <label>
              <span>喜好品类</span>
              <textarea onChange={event => setCategoryText(event.target.value)} value={categoryText} />
            </label>
          </div>
        </aside>
      </section>
    </main>
  )
}

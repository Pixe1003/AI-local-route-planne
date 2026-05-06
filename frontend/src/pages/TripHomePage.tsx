import { CalendarPlus, Clock3, FolderOpen, MapPinned } from "lucide-react"
import { useEffect } from "react"
import { useNavigate } from "react-router-dom"

import { useTripStore } from "../store/tripStore"
import { useUserStore } from "../store/userStore"
import { cityLabel } from "../utils/planning"

export function TripHomePage() {
  const navigate = useNavigate()
  const { userId } = useUserStore()
  const { trips, loading, error, fetchTrips } = useTripStore()

  useEffect(() => {
    fetchTrips(userId)
  }, [fetchTrips, userId])

  return (
    <main className="workspace trip-home">
      <section className="trip-hero">
        <div className="page-title">
          <span className="icon-badge">
            <FolderOpen size={22} />
          </span>
          <div>
            <h1>我的行程</h1>
            <p>Trip Manager Agent 负责读取行程、保存版本，并把推荐池与路线调整串成闭环。</p>
          </div>
        </div>
        <button className="primary-button" onClick={() => navigate("/trips/new")} type="button">
          <CalendarPlus size={18} />
          新建行程
        </button>
      </section>

      {error ? <p className="error-text">{error}</p> : null}

      {trips.length === 0 ? (
        <section className="input-panel trip-empty">
          <MapPinned size={30} />
          <h2>{loading ? "正在读取行程" : "还没有行程"}</h2>
          <p>创建第一条路线后，这里会展示行程摘要、当前版本和可继续调整的入口。</p>
          <button className="secondary-button" onClick={() => navigate("/trips/new")} type="button">
            <CalendarPlus size={18} />
            从新建需求开始
          </button>
        </section>
      ) : (
        <section className="trip-list">
          {trips.map(trip => (
            <button
              className="trip-card"
              key={trip.trip_id}
              onClick={() => navigate(`/trips/${trip.trip_id}`)}
              type="button"
            >
              <div>
                <strong>{trip.title}</strong>
                <span>
                  {cityLabel(trip.city)} · {trip.date} · {trip.version_count} 个版本
                </span>
              </div>
              <p>{trip.cover_poi_names.length ? trip.cover_poi_names.join(" / ") : "暂无点位摘要"}</p>
              <small>
                <Clock3 size={14} />
                {new Date(trip.updated_at).toLocaleString()}
              </small>
            </button>
          ))}
        </section>
      )}
    </main>
  )
}

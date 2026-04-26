import { CalendarDays, MapPinned, Sparkles } from "lucide-react"
import { FormEvent, useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"

import { getPersonas } from "../api/meta"
import { TagSelector } from "../components/TagSelector"
import { usePoolStore } from "../store/poolStore"
import { useUserStore } from "../store/userStore"
import type { PersonaOption } from "../types/user"

const fallbackPersonas: PersonaOption[] = [
  { value: "couple", label: "情侣约会" },
  { value: "foodie", label: "探店达人" },
  { value: "photographer", label: "打卡拍照" },
  { value: "literary", label: "文艺青年" },
  { value: "friends", label: "朋友聚会" },
  { value: "solo", label: "独自出行" }
]

export function HomePage() {
  const navigate = useNavigate()
  const { userId, personaTags, paceStyle, setPersonaTags, setPaceStyle } = useUserStore()
  const { fetchPool, loading, error } = usePoolStore()
  const [personas, setPersonas] = useState(fallbackPersonas)
  const [freeText, setFreeText] = useState("不想排队太久，想要适合拍照和吃饭")
  const [date, setDate] = useState("2026-05-02")
  const [start, setStart] = useState("13:00")
  const [end, setEnd] = useState("21:00")
  const [budget, setBudget] = useState(300)

  useEffect(() => {
    getPersonas().then(setPersonas).catch(() => setPersonas(fallbackPersonas))
  }, [])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    await fetchPool({
      user_id: userId,
      city: "shanghai",
      date,
      time_window: { start, end },
      persona_tags: personaTags,
      pace_style: paceStyle,
      party: personaTags.includes("couple") ? "couple" : "friends",
      budget_per_person: budget,
      free_text: freeText
    })
    navigate("/pool")
  }

  return (
    <main className="workspace home-grid">
      <section className="input-panel">
        <div className="page-title">
          <span className="icon-badge">
            <MapPinned size={22} />
          </span>
          <div>
            <h1>AI 本地路线智能规划</h1>
            <p>上海 · 周末半日路线 · 个性化 POI 推荐</p>
          </div>
        </div>
        <form className="planner-form" onSubmit={submit}>
          <label>
            <span>城市</span>
            <input readOnly value="上海" />
          </label>
          <div className="form-row">
            <label>
              <span>日期</span>
              <input onChange={event => setDate(event.target.value)} type="date" value={date} />
            </label>
            <label>
              <span>预算</span>
              <input
                min={0}
                onChange={event => setBudget(Number(event.target.value))}
                type="number"
                value={budget}
              />
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
          <div className="field-group">
            <span>人群标签</span>
            <TagSelector onChange={setPersonaTags} options={personas} value={personaTags} />
          </div>
          <div className="segmented">
            {["balanced", "relaxed", "efficient"].map(style => (
              <button
                className={paceStyle === style ? "active" : ""}
                key={style}
                onClick={() => setPaceStyle(style)}
                type="button"
              >
                {style === "balanced" ? "平衡" : style === "relaxed" ? "松弛" : "高效"}
              </button>
            ))}
          </div>
          <label>
            <span>补充偏好</span>
            <textarea onChange={event => setFreeText(event.target.value)} value={freeText} />
          </label>
          {error ? <p className="error-text">{error}</p> : null}
          <button className="primary-button mobile-action-bar" disabled={loading} type="submit">
            <Sparkles size={18} />
            {loading ? "生成中" : "生成推荐池"}
          </button>
        </form>
      </section>
      <aside className="summary-panel">
        <CalendarDays size={22} />
        <h2>Demo 验收场景</h2>
        <p>上海 + 周六下午 + 情侣 + 探店达人，推荐池会默认勾选 3-5 个 POI。</p>
        <div className="metric-grid">
          <span>2-3</span>
          <small>路线方案</small>
          <span>15+</span>
          <small>候选 POI</small>
          <span>4</span>
          <small>调整意图</small>
        </div>
      </aside>
    </main>
  )
}

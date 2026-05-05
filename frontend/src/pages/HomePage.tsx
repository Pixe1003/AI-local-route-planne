import { CalendarDays, ClipboardCheck, MapPinned, Search, Sparkles } from "lucide-react"
import { FormEvent, useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"

import { analyzeOnboarding, buildNeedProfile } from "../api/onboarding"
import { getPersonas } from "../api/meta"
import { TagSelector } from "../components/TagSelector"
import { usePoolStore } from "../store/poolStore"
import { useUserStore } from "../store/userStore"
import type { OnboardingAnalyzeResponse } from "../types/onboarding"
import type { PersonaOption } from "../types/user"

const fallbackPersonas: PersonaOption[] = [
  { value: "couple", label: "情侣约会" },
  { value: "foodie", label: "探店达人" },
  { value: "photographer", label: "打卡拍照" },
  { value: "literary", label: "文艺青年" },
  { value: "friends", label: "朋友聚会" },
  { value: "solo", label: "独自出行" }
]

const quickTags: PersonaOption[] = [
  { value: "half_day", label: "半天" },
  { value: "night", label: "夜游" },
  { value: "avoid_queue", label: "少排队" },
  { value: "local_food", label: "本地美食" },
  { value: "photogenic", label: "小众拍照" },
  { value: "rainy", label: "雨天室内" },
  { value: "family", label: "亲子" },
  { value: "senior", label: "带老人" }
]

export function HomePage() {
  const navigate = useNavigate()
  const {
    userId,
    personaTags,
    paceStyle,
    needProfile,
    setNeedProfile,
    setPersonaTags,
    setPaceStyle
  } = useUserStore()
  const { fetchPool, loading, error } = usePoolStore()
  const [personas, setPersonas] = useState(fallbackPersonas)
  const [freeText, setFreeText] = useState("今天 14:00 到 20:00 在上海从人民广场出发，情侣想拍照吃本地菜，人均 180，少排队")
  const [selectedQuickTags, setSelectedQuickTags] = useState(["avoid_queue", "local_food", "photogenic"])
  const [date, setDate] = useState("2026-05-02")
  const [start, setStart] = useState("14:00")
  const [end, setEnd] = useState("20:00")
  const [budget, setBudget] = useState(180)
  const [analysis, setAnalysis] = useState<OnboardingAnalyzeResponse | null>(null)
  const [analysisLoading, setAnalysisLoading] = useState(false)

  useEffect(() => {
    getPersonas().then(setPersonas).catch(() => setPersonas(fallbackPersonas))
  }, [])

  const composedQuery = () => {
    const labels = quickTags
      .filter(tag => selectedQuickTags.includes(tag.value))
      .map(tag => tag.label)
      .join("、")
    return labels ? `${freeText}。偏好：${labels}` : freeText
  }

  const partyType = () => {
    if (personaTags.includes("couple")) return "couple"
    if (personaTags.includes("solo")) return "solo"
    if (selectedQuickTags.includes("family")) return "family"
    if (selectedQuickTags.includes("senior")) return "senior"
    return "friends"
  }

  const analyze = async () => {
    setAnalysisLoading(true)
    try {
      setAnalysis(await analyzeOnboarding(composedQuery()))
    } finally {
      setAnalysisLoading(false)
    }
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const query = composedQuery()
    const profile = (
      await buildNeedProfile(query, {
        city: "shanghai",
        date,
        start_time: start,
        end_time: end,
        budget_per_person: budget,
        party_type: partyType(),
        activity_preferences: selectedQuickTags.includes("photogenic") ? ["拍照", "打卡"] : [],
        food_preferences: selectedQuickTags.includes("local_food") ? ["本地菜", "美食"] : [],
        route_style: [
          paceStyle === "relaxed" ? "轻松" : paceStyle === "efficient" ? "高效" : "平衡",
          ...quickTags.filter(tag => selectedQuickTags.includes(tag.value)).map(tag => tag.label)
        ]
      })
    ).profile
    setNeedProfile(profile)
    await fetchPool({
      user_id: userId,
      city: "shanghai",
      date,
      time_window: { start, end },
      persona_tags: personaTags,
      pace_style: paceStyle,
      party: partyType(),
      budget_per_person: budget,
      free_text: query,
      need_profile: profile
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
            <h1>今天想怎么玩？</h1>
            <p>自然语言 + 快捷标签先补齐需求，再生成可校验路线。</p>
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
            <span>快捷标签</span>
            <TagSelector onChange={setSelectedQuickTags} options={quickTags} value={selectedQuickTags} />
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
            <span>自然语言需求</span>
            <textarea onChange={event => setFreeText(event.target.value)} value={freeText} />
          </label>
          <div className="onboarding-actions">
            <button className="secondary-button" disabled={analysisLoading} onClick={analyze} type="button">
              <Search size={18} />
              {analysisLoading ? "分析中" : "分析缺失信息"}
            </button>
            <span>
              完整度 {Math.round((analysis?.completeness_score ?? needProfile?.completeness_score ?? 0) * 100)}%
            </span>
          </div>
          <section className="need-card">
            <div>
              <ClipboardCheck size={20} />
              <h2>本次路线需求</h2>
            </div>
            <p>
              {start}-{end} · {partyType()} · 人均 ¥{budget} ·{" "}
              {selectedQuickTags
                .map(value => quickTags.find(tag => tag.value === value)?.label)
                .filter(Boolean)
                .join("、")}
            </p>
            {analysis?.should_ask_followup ? (
              <ul>
                {analysis.suggested_questions.map(question => (
                  <li key={question}>{question}</li>
                ))}
              </ul>
            ) : (
              <small>信息充足时会直接进入推荐池；缺关键槽位时会在这里提示补充。</small>
            )}
          </section>
          {error ? <p className="error-text">{error}</p> : null}
          <button className="primary-button mobile-action-bar" disabled={loading} type="submit">
            <Sparkles size={18} />
            {loading ? "生成中" : "生成推荐池"}
          </button>
        </form>
      </section>
      <aside className="summary-panel">
        <CalendarDays size={22} />
        <h2>Harness Agent 闭环</h2>
        <p>Onboarding 生成画像，Planner 做召回/评分/校验，Replanner 根据事件动态调整。</p>
        <div className="metric-grid">
          <span>0.8</span>
          <small>完整度阈值</small>
          <span>DAG</span>
          <small>工具编排</small>
          <span>2x</span>
          <small>失败修复</small>
        </div>
      </aside>
    </main>
  )
}

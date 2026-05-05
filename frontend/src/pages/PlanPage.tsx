import { ArrowLeft, Send } from "lucide-react"
import { FormEvent, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"

import { PlanCompare } from "../components/PlanCompare"
import { PlanMap } from "../components/PlanMap"
import { PlanTimeline } from "../components/PlanTimeline"
import { usePlanStore } from "../store/planStore"

const replanShortcuts = ["少排队", "更省钱", "少走路", "雨天方案", "亲子友好", "老人友好", "压缩到 2 小时"]

export function PlanPage() {
  const navigate = useNavigate()
  const { plans, activePlanId, switchPlan, sendAdjustment, loading, chatHistory } = usePlanStore()
  const [highlighted, setHighlighted] = useState(0)
  const [message, setMessage] = useState("把第二站换成不需要排队的")
  const activePlan = useMemo(
    () => plans.find(plan => plan.plan_id === activePlanId) ?? plans[0],
    [activePlanId, plans]
  )

  if (!activePlan) {
    return (
      <main className="workspace empty-state">
        <h1>还没有路线方案</h1>
        <button className="secondary-button" onClick={() => navigate("/pool")} type="button">
          <ArrowLeft size={18} /> 返回推荐池
        </button>
      </main>
    )
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!message.trim()) return
    await sendAdjustment(message)
    setMessage("")
  }

  return (
    <main className="workspace plan-workspace">
      <div className="topbar">
        <button className="icon-button" onClick={() => navigate("/pool")} title="返回" type="button">
          <ArrowLeft size={18} />
        </button>
        <div>
          <h1>{activePlan.title}</h1>
          <p>{activePlan.description}</p>
        </div>
      </div>
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
      <section className="replan-panel">
        {replanShortcuts.map(shortcut => (
          <button className="secondary-button" disabled={loading} key={shortcut} onClick={() => sendAdjustment(shortcut)} type="button">
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
          <input onChange={event => setMessage(event.target.value)} value={message} />
          <button className="icon-button filled" disabled={loading} title="调整" type="submit">
            <Send size={18} />
          </button>
        </div>
      </form>
    </main>
  )
}

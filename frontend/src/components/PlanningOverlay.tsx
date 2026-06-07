import { Bot, CheckCircle2 } from "lucide-react"

import { useAgentPlanningStore } from "../store/agentPlanningStore"

export function PlanningOverlay() {
  const { active, currentLabel, progress, steps } = useAgentPlanningStore()

  if (!active) return null

  return (
    <div className="planning-overlay" role="status" aria-live="polite">
      <svg className="planning-route-svg" viewBox="0 0 680 360" aria-hidden="true">
        <path className="planning-route-shadow" d="M48 288 C156 174 230 306 328 184 S492 88 628 164" />
        <path className="planning-route-line" d="M48 288 C156 174 230 306 328 184 S492 88 628 164" />
        <circle className="planning-node first" cx="48" cy="288" r="9" />
        <circle className="planning-node second" cx="328" cy="184" r="9" />
        <circle className="planning-node third" cx="628" cy="164" r="9" />
      </svg>
      <div className="planning-bubble">
        <Bot size={22} />
        <div>
          <strong>{currentLabel}</strong>
          <div className="planning-progress">
            <span style={{ width: `${progress}%` }} />
          </div>
          <div className="planning-step-tags">
            {steps.map(step => (
              <span key={step}>
                <CheckCircle2 size={13} />
                {step}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

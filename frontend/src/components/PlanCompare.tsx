import type { RefinedPlan } from "../types/plan"

interface PlanCompareProps {
  plans: RefinedPlan[]
  activePlanId: string
  onSwitch: (planId: string) => void
}

export function PlanCompare({ plans, activePlanId, onSwitch }: PlanCompareProps) {
  const baseline = plans[0]

  return (
    <div className="plan-tabs">
      {plans.map(plan => {
        const durationDiff = baseline ? plan.summary.total_duration_min - baseline.summary.total_duration_min : 0
        return (
          <button
            className={plan.plan_id === activePlanId ? "plan-tab active" : "plan-tab"}
            key={plan.plan_id}
            onClick={() => onSwitch(plan.plan_id)}
            type="button"
          >
            <span>{plan.title}</span>
            <strong>{plan.summary.poi_count} 站 · ¥{plan.summary.total_cost}</strong>
            <small>{durationDiff === 0 ? "基准方案" : `${durationDiff > 0 ? "+" : ""}${durationDiff} 分钟`}</small>
          </button>
        )
      })}
    </div>
  )
}

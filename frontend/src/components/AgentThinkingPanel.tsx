import type { AgentToolCall } from "../types/agent"

const labels: Record<string, string> = {
  parse_intent: "在理解需求",
  search_ugc_evidence: "在召回 UGC",
  recommend_pool: "在筛选候选池",
  compose_story: "在编排路线",
  get_amap_chain: "在计算高德路线",
  validate_route: "在校验可行性",
  critique: "最后审稿",
  parse_feedback: "在理解反馈",
  replan_by_event: "在更新路线"
}

interface AgentThinkingPanelProps {
  steps: AgentToolCall[]
}

export function AgentThinkingPanel({ steps }: AgentThinkingPanelProps) {
  if (!steps.length) return null
  return (
    <section className="agent-thinking-panel" aria-label="Agent 思考过程">
      <div className="agent-thinking-heading">
        <span className="eyebrow">Agent 思考</span>
        <strong>{steps.length} 步</strong>
      </div>
      <ol>
        {steps.map((step, index) => (
          <li key={`${step.tool_name}-${index}`}>
            <span>{labels[step.tool_name] ?? step.tool_name}</span>
            {step.observation_summary ? <p>{step.observation_summary}</p> : null}
          </li>
        ))}
      </ol>
    </section>
  )
}

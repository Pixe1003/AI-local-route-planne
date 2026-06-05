import {
  BarChart3,
  Brain,
  CheckCircle2,
  Code2,
  Database,
  Eye,
  FileCode2,
  FlaskConical,
  Gauge,
  GitBranch,
  Layers,
  Map,
  MessageSquare,
  Network,
  RefreshCw,
  Route,
  Search,
  Server,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Target,
  Trophy,
  Workflow,
  Wrench
} from "lucide-react"
import type { LucideIcon } from "lucide-react"

type Metric = {
  label: string
  value: string
  note: string
  tone: "blue" | "green" | "orange" | "red"
}

type ArchitectureStep = {
  icon: LucideIcon
  title: string
  body: string
  detail: string
}

type FlowStep = {
  step: string
  title: string
  interaction: string
  code: string
  output: string
}

type AgentFrame = {
  title: string
  purpose: string
  state: string
  code: string
  tools: string[]
}

type TechChoice = {
  name: string
  choice: string
  reason: string
  code: string
}

type InteractionNode = {
  icon: LucideIcon
  title: string
  body: string
  code: string
}

const metrics: Metric[] = [
  {
    label: "硬约束满足率",
    value: "100%",
    note: "5 个基准场景覆盖时间窗、预算、必到、类别约束",
    tone: "green"
  },
  {
    label: "解释忠实度",
    value: "1.000",
    note: "推荐理由可回查 POI、UGC 证据与评分拆解",
    tone: "blue"
  },
  {
    label: "最优解 gap",
    value: "0.001",
    note: "相对 CP-SAT / exact oracle 的路线质量差距",
    tone: "orange"
  },
  {
    label: "Ranker NDCG@5",
    value: "+95.1%",
    note: "LightGBM LambdaMART 相对规则基线提升",
    tone: "green"
  },
  {
    label: "Pareto 方案",
    value: "5 条",
    note: "兴趣、均衡、省时、省钱、少排队的非支配解",
    tone: "blue"
  },
  {
    label: "准时概率",
    value: "0.951",
    note: "Monte Carlo 500 次扰动模拟得到的路线稳健性",
    tone: "red"
  }
]

const architecture: ArchitectureStep[] = [
  {
    icon: Brain,
    title: "LLM Agent 编排",
    body: "自然语言请求先进入 plan-act-observe harness，LLM 只负责选择白名单工具。",
    detail: "Conductor.MAX_STEPS = 12"
  },
  {
    icon: Database,
    title: "RAG 与用户记忆",
    body: "UGC、POI、历史会话和 user_facts 共同决定候选池，证据带 provenance。",
    detail: "FAISS + bge-small-zh + SQLite"
  },
  {
    icon: BarChart3,
    title: "学习排序",
    body: "线上评分器直接参与训练特征生成，降低 train/serve skew。",
    detail: "PoiScoringService + LambdaMART"
  },
  {
    icon: Route,
    title: "约束路线优化",
    body: "把路线规划建成带时间窗的 OPTW，而不是让 LLM 直接生成路线。",
    detail: "OR-Tools CP-SAT + exact + greedy"
  },
  {
    icon: ShieldCheck,
    title: "校验与稳健性",
    body: "路线生成后再校验硬约束，并跑 Monte Carlo 估计准时概率。",
    detail: "validate_route + assess_robustness"
  },
  {
    icon: Map,
    title: "前端演示闭环",
    body: "React H5 展示 Pareto 卡片、高德路线、Agent 思考过程和反馈改写。",
    detail: "Vite + React + Zustand"
  }
]

const endToEndFlow: FlowStep[] = [
  {
    step: "01",
    title: "前端收集意图与偏好",
    interaction: "用户在 UGC 发现流里点赞 POI，再填写一句自然语言请求、日期、时间窗、预算、起点半径。",
    code: "frontend/src/pages/DiscoveryFeedPage.tsx -> submit(), buildProfile(), syncSnapshot(), runAgentRoute()",
    output: "AgentRunRequest：free_text、need_profile、preference_snapshot、origin、time_window"
  },
  {
    step: "02",
    title: "API 构造 AgentState",
    interaction: "/api/agent/run 接收请求，补齐 PlanContext、UserNeedProfile，并加载 episodic、semantic、vector 三层记忆。",
    code: "backend/app/api/routes_agent.py -> run_agent(), build_initial_state(), _enrich_initial_memory()",
    output: "AgentState：goal、context、profile、preference、memory、trace_id"
  },
  {
    step: "03",
    title: "Conductor 决策下一步工具",
    interaction: "每轮先走规则 fallback，若开启 LLM tool calling 且没有 fast decision，再让 LLM 从工具 schema 中选择下一步。",
    code: "backend/app/agent/conductor.py -> _decide(), _rule_based_decision(), _apply_result()",
    output: "ToolCall 记录 latency、tokens、observation_summary，并 patch AgentMemory"
  },
  {
    step: "04",
    title: "召回证据并生成候选池",
    interaction: "先查 UGC 语义证据，再由 PoolService 结合 FAISS、SQLite、偏好快照、user_facts 和距离半径做候选池。",
    code: "backend/app/agent/tools.py -> _search_ugc_evidence(), _recommend_pool(); backend/app/services/pool_service.py",
    output: "PoolResponse：categories、PoiInPool、score_breakdown、evidence_snippets、default_selected_ids"
  },
  {
    step: "05",
    title: "约束优化与 Pareto 前沿",
    interaction: "把候选 POI 转成 OptwNode，加入营业时间、预算、must visit、类别组和旅行时间矩阵，再求多目标非支配解。",
    code: "backend/app/agent/tools.py -> _solve_constrained_route(); backend/app/solver/optw.py; backend/app/solver/pareto.py",
    output: "route_optimization、route_variants、pool.default_selected_ids"
  },
  {
    step: "06",
    title: "故事、实路网、校验、审查",
    interaction: "StoryAgent 只从候选证据里写路线解释，高德链路生成 GeoJSON，Validator 和 Critic 负责交付前审查。",
    code: "story_agent.py, routes_route.py, route_validator.py, critic.py, montecarlo.py",
    output: "story_plan、route_chain、validation、robustness、critique"
  },
  {
    step: "07",
    title: "前端展示与反馈改写",
    interaction: "AmapRoutePage 从 Zustand 读取 Agent 结果，展示地图、路线点、Pareto 卡片和 AgentThinkingPanel；反馈走 /agent/adjust。",
    code: "frontend/src/pages/AmapRoutePage.tsx -> submitFeedback(); frontend/src/components/AgentThinkingPanel.tsx",
    output: "可交互 H5 路线页，支持二次改写、重新取高德链路、刷新稳健性"
  }
]

const agentFrames: AgentFrame[] = [
  {
    title: "Conductor：状态机和预算控制",
    purpose: "把一次路线规划限制在 12 步内，每一步都必须是 ToolRegistry 暴露的工具或 finish。",
    state: "phase 从 UNDERSTANDING 到 RETRIEVING、COMPOSING、CHECKING、PRESENTING、DONE。",
    code: "backend/app/agent/conductor.py",
    tools: ["_decide", "_rule_based_decision", "tracer.start_as_current_span", "TOOL_LATENCY"]
  },
  {
    title: "AgentState：跨工具共享的 typed memory",
    purpose: "所有工具不直接互相调用，而是读写 AgentMemory，降低链路耦合并支持持久化恢复。",
    state: "intent、ugc_hits、pool、route_optimization、story_plan、route_chain、validation、robustness、critique。",
    code: "backend/app/agent/state.py",
    tools: ["AgentGoal", "ToolCall", "AgentMemory", "AgentPhase"]
  },
  {
    title: "ToolRegistry：LLM 可见能力边界",
    purpose: "把工具名、schema、handler 绑定在一起，LLM 只能选择注册过的工具，避免自由生成不可控动作。",
    state: "schemas_for_llm() 暴露工具 schema；execute() 只按注册表执行 handler。",
    code: "backend/app/agent/tools.py",
    tools: ["parse_intent", "recommend_pool", "solve_constrained_route", "critique"]
  },
  {
    title: "Specialists：专业子能力",
    purpose: "StoryAgent 负责解释，Critic 负责审查，RepairAgent 负责反馈解析，避免一个大 prompt 承担所有职责。",
    state: "每个 specialist 都有规则 fallback；StoryAgent 还有 hallucinated_poi / hallucinated_ugc post_check。",
    code: "backend/app/agent/specialists/",
    tools: ["StoryAgent.compose", "Critic.review", "RepairAgent.parse"]
  }
]

const toolPipeline = [
  "parse_intent",
  "recall_similar_sessions",
  "search_ugc_evidence",
  "recommend_pool",
  "solve_constrained_route",
  "compose_story",
  "get_amap_chain",
  "validate_route",
  "assess_robustness",
  "critique",
  "parse_feedback",
  "replan_by_event"
]

const techChoices: TechChoice[] = [
  {
    name: "FastAPI + Pydantic v2",
    choice: "后端 API 和 Agent 响应都用 typed schema",
    reason: "路线规划链路字段多、状态多，Pydantic 能把 AgentState、PoolResponse、RouteChainResponse 的契约固定住。",
    code: "backend/app/api/routes_agent.py, backend/app/schemas/"
  },
  {
    name: "React + Vite + Zustand",
    choice: "H5 演示端走轻量状态管理",
    reason: "路线生成后需要跨页面保存 pool、story_plan、route_variants 和 route_chain，Zustand 比全局复杂状态机更贴合当前规模。",
    code: "frontend/src/store/amapRouteStore.ts, frontend/src/pages/AmapRoutePage.tsx"
  },
  {
    name: "SQLite",
    choice: "会话、user_facts、本地 POI 与高德缓存优先本地化",
    reason: "Hackathon 演示和评测要可复跑，SQLite 不依赖外部服务，失败面小，方便一键测试。",
    code: "backend/app/agent/store.py, backend/app/repositories/sqlite_poi_repo.py"
  },
  {
    name: "FAISS + bge-small-zh",
    choice: "中文 POI / UGC 语义检索",
    reason: "用户输入是自然语言，关键词不足以稳定召回；FAISS 本地索引能同时保留 provenance 和低延迟。",
    code: "backend/app/services/retrieval_service.py, backend/app/repositories/faiss_index.py"
  },
  {
    name: "LightGBM LambdaMART",
    choice: "POI 候选重排",
    reason: "问题本质是 listwise 排序，LambdaMART 比单点打分更贴合 NDCG@5；模型缺失时 PoiRanker.predict 返回 None 自动回退规则分。",
    code: "backend/app/ml/ranker.py, backend/app/services/poi_scoring_service.py"
  },
  {
    name: "OR-Tools CP-SAT",
    choice: "OPTW 硬约束求解",
    reason: "时间窗、预算、营业时间、must visit 和类别组是硬约束，交给求解器比 prompt 或启发式排序更可解释、可回归。",
    code: "backend/app/solver/optw.py -> solve_optw()"
  },
  {
    name: "Monte Carlo",
    choice: "路线稳健性估计",
    reason: "排队、停留、路段耗时都有随机扰动，单条最短路线不等于真实可执行路线；准时概率能补足路线质量维度。",
    code: "backend/app/sim/montecarlo.py, backend/app/agent/tools.py -> _assess_robustness()"
  },
  {
    name: "Prometheus + OpenTelemetry",
    choice: "工具级延迟、成本和 trace 可观测",
    reason: "Agent 链路长，必须知道慢在哪个工具、是否降级、token 和成本怎样分布。",
    code: "backend/app/observability/, backend/app/agent/conductor.py"
  }
]

const interactionNodes: InteractionNode[] = [
  {
    icon: MessageSquare,
    title: "用户输入与反馈",
    body: "用户在 H5 中收藏 UGC、填写自然语言诉求，后续也可以继续提交用户反馈改写路线。",
    code: "free_text / preference_snapshot / parent_session_id"
  },
  {
    icon: Sparkles,
    title: "H5 前端",
    body: "DiscoveryFeedPage 组装请求，AmapRoutePage 保存结果并展示地图、Pareto、Agent 思考过程。",
    code: "runAgentRoute() / adjustAgentRoute()"
  },
  {
    icon: Server,
    title: "Agent API",
    body: "FastAPI 把请求转换为 AgentState，补齐上下文、用户画像、历史记忆和 trace id。",
    code: "build_initial_state() / build_adjust_state()"
  },
  {
    icon: Brain,
    title: "Conductor",
    body: "状态机逐步选择 ToolRegistry 工具；LLM 可以决策，但必须受白名单 schema 约束。",
    code: "_decide() / _rule_based_decision()"
  },
  {
    icon: Search,
    title: "检索与记忆",
    body: "召回 UGC、POI、user_facts、similar_sessions，为推荐理由和候选池提供证据。",
    code: "search_ugc_evidence / recall_similar_sessions"
  },
  {
    icon: SlidersHorizontal,
    title: "排序与求解",
    body: "PoolService 重排 POI，OPTW 求解硬约束路线，Pareto 输出多目标非支配方案。",
    code: "PoiScoringService / solve_optw() / build_pareto_variants()"
  },
  {
    icon: Map,
    title: "地图与路线",
    body: "StoryAgent 生成可溯源解释，高德链路生成真实路网 GeoJSON，前端渲染路线点位。",
    code: "compose_story / get_amap_chain / AmapRouteMap"
  },
  {
    icon: Eye,
    title: "评测与可观测",
    body: "Validator、Critic、Monte Carlo、Prometheus 与 OpenTelemetry 共同兜住质量和稳定性。",
    code: "validate_route / critique / assess_robustness"
  }
]

const timeline = [
  {
    phase: "01",
    title: "产品入口",
    items: ["UGC 发现流", "偏好冷启动", "自然语言即时路线"]
  },
  {
    phase: "02",
    title: "Agent Harness",
    items: ["工具白名单", "状态持久化", "Critic 幻觉检查"]
  },
  {
    phase: "03",
    title: "算法内核",
    items: ["OPTW 建模", "CP-SAT 求解", "Pareto 多目标前沿"]
  },
  {
    phase: "04",
    title: "数据与 ML",
    items: ["FAISS 检索", "LambdaMART Ranker", "跨会话记忆召回"]
  },
  {
    phase: "05",
    title: "质量闭环",
    items: ["5 场景 eval", "CI gate", "latency bench"]
  }
]

const learnings = [
  "LLM 用于决策编排，不用于直接生成关键路线结果。",
  "约束优化负责路线选择，解释必须回查真实证据。",
  "训练与服务特征同源，是 Ranker 指标提升的关键。",
  "每个外部依赖都需要确定性 fallback，演示才不会被 key 或网络状态卡住。"
]

const nextSteps = [
  "接入实时天气、路况、排队与优惠事件流。",
  "为重复请求增加 OPTW 解缓存，继续压缩 p95 延迟。",
  "用真实 LLM key 补齐 rule / llm 模式的成本与质量对照。",
  "扩展多人偏好聚合，把单人路线升级为小组决策。"
]

const sourceGroups = [
  {
    title: "前端交互",
    files: [
      "frontend/src/pages/DiscoveryFeedPage.tsx",
      "frontend/src/pages/AmapRoutePage.tsx",
      "frontend/src/api/agent.ts",
      "frontend/src/components/AgentThinkingPanel.tsx"
    ]
  },
  {
    title: "Agent 框架",
    files: [
      "backend/app/agent/conductor.py",
      "backend/app/agent/state.py",
      "backend/app/agent/tools.py",
      "backend/app/agent/store.py"
    ]
  },
  {
    title: "算法与数据",
    files: [
      "backend/app/services/pool_service.py",
      "backend/app/services/poi_scoring_service.py",
      "backend/app/ml/ranker.py",
      "backend/app/solver/optw.py",
      "backend/app/solver/pareto.py",
      "backend/app/sim/montecarlo.py"
    ]
  },
  {
    title: "评测与可观测",
    files: [
      "backend/eval/run_eval.py",
      "backend/eval/metrics.py",
      "backend/app/observability/metrics.py",
      "backend/app/api/routes_route.py"
    ]
  }
]

export function ProjectReviewPage() {
  return (
    <main className="project-review-page">
      <section className="review-intro">
        <div className="review-intro-copy">
          <span className="eyebrow">AIroute 项目复盘</span>
          <h1>从路线 Demo 到可验证的 AI 路线规划系统</h1>
          <p>
            AIroute 的核心不是让大模型写一段行程文案，而是把本地路线规划拆成可编排、可优化、可评估、可降级的工程系统。
          </p>
        </div>
        <div className="review-signal-board" aria-label="项目核心链路">
          <div className="signal-route-line" aria-hidden="true" />
          <div className="signal-node active">
            <Sparkles size={18} />
            <span>自然语言</span>
          </div>
          <div className="signal-node">
            <Brain size={18} />
            <span>Agent</span>
          </div>
          <div className="signal-node">
            <Route size={18} />
            <span>OPTW</span>
          </div>
          <div className="signal-node">
            <Trophy size={18} />
            <span>评测 gate</span>
          </div>
        </div>
      </section>

      <nav className="review-anchor-row" aria-label="复盘章节">
        <a href="#metrics">指标</a>
        <a href="#interaction-map">图</a>
        <a href="#flow">链路</a>
        <a href="#agent">Agent</a>
        <a href="#tech">选型</a>
        <a href="#sources">源码</a>
      </nav>

      <section className="review-band" id="metrics">
        <div className="review-section-heading">
          <span className="review-section-icon">
            <Gauge size={18} />
          </span>
          <div>
            <h2>结果证据</h2>
            <p>项目交付用离线评测、性能基准和 CI gate 兜住，而不是只靠主观演示。</p>
          </div>
        </div>
        <div className="review-metric-grid">
          {metrics.map(metric => (
            <article className={`review-metric-card tone-${metric.tone}`} key={metric.label}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
              <p>{metric.note}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="review-band" id="architecture">
        <div className="review-section-heading">
          <span className="review-section-icon">
            <Layers size={18} />
          </span>
          <div>
            <h2>系统架构</h2>
            <p>每层只做自己擅长的事，形成从输入到证据、路线、解释和评测的闭环。</p>
          </div>
        </div>
        <div className="review-architecture-grid">
          {architecture.map(step => {
            const Icon = step.icon
            return (
              <article className="review-architecture-card" key={step.title}>
                <Icon size={22} />
                <h3>{step.title}</h3>
                <p>{step.body}</p>
                <span>{step.detail}</span>
              </article>
            )
          })}
        </div>
      </section>

      <section className="review-band" id="interaction-map">
        <div className="review-section-heading">
          <span className="review-section-icon">
            <Network size={18} />
          </span>
          <div>
            <h2>系统交互图</h2>
            <p>这张图把一次路线请求和一次反馈改写放在同一张交互链路里，展示系统各层如何传递状态与证据。</p>
          </div>
        </div>
        <div className="review-interaction-map" aria-label="AIroute 系统交互图">
          {interactionNodes.map((node, index) => {
            const Icon = node.icon
            return (
              <article className="interaction-node" key={node.title}>
                <span className="interaction-step">{String(index + 1).padStart(2, "0")}</span>
                <Icon size={21} />
                <h3>{node.title}</h3>
                <p>{node.body}</p>
                <code>{node.code}</code>
              </article>
            )
          })}
        </div>
      </section>

      <section className="review-band" id="flow">
        <div className="review-section-heading">
          <span className="review-section-icon">
            <Workflow size={18} />
          </span>
          <div>
            <h2>端到端交互链路</h2>
            <p>一次“现在出发”的路线请求，会从 H5 表单一路流经 Agent、检索、优化、地图和反馈改写。</p>
          </div>
        </div>
        <ol className="review-flow-list">
          {endToEndFlow.map(item => (
            <li key={item.step}>
              <span className="review-flow-index">{item.step}</span>
              <div>
                <h3>{item.title}</h3>
                <p>{item.interaction}</p>
                <code>{item.code}</code>
                <small>{item.output}</small>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="review-band" id="agent">
        <div className="review-section-heading">
          <span className="review-section-icon">
            <Network size={18} />
          </span>
          <div>
            <h2>Agent 内部框架</h2>
            <p>Agent 的关键不是“一个大模型回答”，而是状态机、工具注册、typed memory 和专业子 Agent 的组合。</p>
          </div>
        </div>
        <div className="review-agent-layout">
          <div className="review-agent-cards">
            {agentFrames.map(frame => (
              <article className="review-agent-card" key={frame.title}>
                <h3>{frame.title}</h3>
                <p>{frame.purpose}</p>
                <small>{frame.state}</small>
                <code>{frame.code}</code>
                <div className="review-chip-row">
                  {frame.tools.map(tool => (
                    <span key={tool}>{tool}</span>
                  ))}
                </div>
              </article>
            ))}
          </div>
          <aside className="review-tool-stack" aria-label="Agent 工具链">
            <div className="review-tool-heading">
              <Wrench size={18} />
              <strong>ToolRegistry 工具链</strong>
            </div>
            <ol>
              {toolPipeline.map(tool => (
                <li key={tool}>{tool}</li>
              ))}
            </ol>
          </aside>
        </div>
      </section>

      <section className="review-band" id="tech">
        <div className="review-section-heading">
          <span className="review-section-icon">
            <SlidersHorizontal size={18} />
          </span>
          <div>
            <h2>技术选型</h2>
            <p>选型围绕三个目标：可复跑、可解释、可降级。每个技术点都对应一段工程边界。</p>
          </div>
        </div>
        <div className="review-tech-grid">
          {techChoices.map(choice => (
            <article className="review-tech-card" key={choice.name}>
              <h3>{choice.name}</h3>
              <strong>{choice.choice}</strong>
              <p>{choice.reason}</p>
              <code>{choice.code}</code>
            </article>
          ))}
        </div>
      </section>

      <section className="review-band" id="timeline">
        <div className="review-section-heading">
          <span className="review-section-icon">
            <GitBranch size={18} />
          </span>
          <div>
            <h2>阶段梳理</h2>
            <p>项目从可演示入口，逐步补齐算法深度、数据证据、工程质量和回归体系。</p>
          </div>
        </div>
        <ol className="review-timeline">
          {timeline.map(item => (
            <li key={item.phase}>
              <span>{item.phase}</span>
              <div>
                <h3>{item.title}</h3>
                <p>{item.items.join(" / ")}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="review-reflection-grid" id="reflection">
        <div className="review-band compact-band">
          <div className="review-section-heading">
            <span className="review-section-icon">
              <CheckCircle2 size={18} />
            </span>
            <div>
              <h2>做对了什么</h2>
              <p>这些决策让项目从 Hackathon 演示变成可复跑系统。</p>
            </div>
          </div>
          <ul className="review-check-list">
            {learnings.map(item => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>

        <div className="review-band compact-band">
          <div className="review-section-heading">
            <span className="review-section-icon">
              <Target size={18} />
            </span>
            <div>
              <h2>下一轮重点</h2>
              <p>当前体系已经可验证，下一步应优先补实时信号和性能缓存。</p>
            </div>
          </div>
          <ul className="review-check-list next-list">
            {nextSteps.map(item => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </section>

      <section className="review-band" id="sources">
        <div className="review-section-heading">
          <span className="review-section-icon">
            <Code2 size={18} />
          </span>
          <div>
            <h2>代码依据索引</h2>
            <p>复盘页中的每个判断都能回到具体模块，适合作为技术答辩和代码走查的讲稿目录。</p>
          </div>
        </div>
        <div className="review-source-group-grid">
          {sourceGroups.map(group => (
            <article className="review-source-group" key={group.title}>
              <h3>{group.title}</h3>
              <div className="review-source-grid">
                {group.files.map(path => (
                  <code key={path}>{path}</code>
                ))}
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="review-band review-summary-band">
        <div className="review-summary-item">
          <MessageSquare size={20} />
          <span>输入是自然语言，但关键决策落在结构化 state 和工具调用上。</span>
        </div>
        <div className="review-summary-item">
          <Search size={20} />
          <span>解释来自 UGC / POI / score_breakdown，而不是模型临场编造。</span>
        </div>
        <div className="review-summary-item">
          <FlaskConical size={20} />
          <span>评测通过 TestClient 复跑真实 API，并用 gate 拦截质量回归。</span>
        </div>
        <div className="review-summary-item">
          <RefreshCw size={20} />
          <span>反馈改写复用父会话状态，只清空路线链、校验、稳健性和审查结果。</span>
        </div>
        <div className="review-summary-item">
          <Eye size={20} />
          <span>每个工具都有 latency、trace、observation，便于定位慢点和失败点。</span>
        </div>
        <div className="review-summary-item">
          <Server size={20} />
          <span>本地数据和 fallback 让无 key、无模型、无索引时仍可演示核心链路。</span>
        </div>
        <div className="review-summary-item">
          <FileCode2 size={20} />
          <span>代码结构按 API、Agent、services、solver、eval 分层，复盘可以逐层讲。</span>
        </div>
      </section>
    </main>
  )
}

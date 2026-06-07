import { create } from "zustand"

interface AgentPlanningState {
  active: boolean
  currentLabel: string
  progress: number
  steps: string[]
  start: (label?: string) => void
  pushStep: (label: string) => void
  finish: () => void
}

export const useAgentPlanningStore = create<AgentPlanningState>((set, get) => ({
  active: false,
  currentLabel: "",
  progress: 0,
  steps: [],
  start: (label = "理解你的偏好和已收藏地点") =>
    set({
      active: true,
      currentLabel: label,
      progress: 18,
      steps: [label]
    }),
  pushStep: label => {
    const steps = [...get().steps, label].slice(-4)
    set({
      currentLabel: label,
      progress: Math.min(92, get().progress + 22),
      steps
    })
  },
  finish: () =>
    set({
      active: false,
      currentLabel: "",
      progress: 100,
      steps: []
    })
}))

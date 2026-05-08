import { create } from "zustand"

import { adjustPlan } from "../api/chat"
import { generatePlans } from "../api/plan"
import type { ChatResponse, ChatTurn } from "../types/chat"
import type { AlternativePoi, PlanRequest, PlanResponse, RefinedPlan } from "../types/plan"

interface PlanStore {
  plans: RefinedPlan[]
  activePlanId: string | null
  loading: boolean
  error: string | null
  chatHistory: ChatTurn[]
  generatePlans: (params: PlanRequest) => Promise<PlanResponse | null>
  switchPlan: (planId: string) => void
  setPlansFromVersion: (plans: RefinedPlan[], activePlanId?: string | null) => void
  applyAdjustment: (response: ChatResponse) => void
  sendAdjustment: (message: string) => Promise<ChatResponse | null>
  replaceWithAlternative: (candidate: AlternativePoi) => Promise<ChatResponse | null>
}

export const usePlanStore = create<PlanStore>((set, get) => ({
  plans: [],
  activePlanId: null,
  loading: false,
  error: null,
  chatHistory: [],
  generatePlans: async params => {
    set({ loading: true, error: null })
    try {
      const response = await generatePlans(params)
      set({
        plans: response.plans,
        activePlanId: response.plans[0]?.plan_id ?? null,
        loading: false
      })
      return response
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : "方案生成失败"
      })
      return null
    }
  },
  switchPlan: planId => set({ activePlanId: planId }),
  setPlansFromVersion: (plans, activePlanId) =>
    set({
      plans,
      activePlanId: activePlanId ?? plans[0]?.plan_id ?? null,
      chatHistory: [],
      error: null
    }),
  applyAdjustment: response => {
    if (!response.updated_plan) return
    const plans = get().plans.map(plan =>
      plan.plan_id === response.updated_plan?.plan_id ? response.updated_plan : plan
    )
    set({
      plans,
      activePlanId: response.updated_plan.plan_id,
      chatHistory: [
        ...get().chatHistory,
        {
          role: "assistant",
          content: response.assistant_message,
          timestamp: new Date().toISOString()
        }
      ]
    })
  },
  sendAdjustment: async message => {
    const activePlanId = get().activePlanId
    if (!activePlanId) return null
    const userTurn: ChatTurn = {
      role: "user",
      content: message,
      timestamp: new Date().toISOString()
    }
    set({ loading: true, chatHistory: [...get().chatHistory, userTurn] })
    try {
      const response = await adjustPlan({
        plan_id: activePlanId,
        user_message: message,
        chat_history: [...get().chatHistory, userTurn]
      })
      get().applyAdjustment(response)
      set({ loading: false })
      return response
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : "调整失败"
      })
      return null
    }
  },
  replaceWithAlternative: async candidate => {
    const activePlanId = get().activePlanId
    if (!activePlanId) return null
    const userTurn: ChatTurn = {
      role: "user",
      content: `替换为 ${candidate.poi_name}`,
      timestamp: new Date().toISOString()
    }
    set({ loading: true, chatHistory: [...get().chatHistory, userTurn] })
    try {
      const response = await adjustPlan({
        plan_id: activePlanId,
        user_message: userTurn.content,
        chat_history: [...get().chatHistory, userTurn],
        action_type: "replace_stop",
        target_stop_index: candidate.replace_stop_index ?? 0,
        replacement_poi_id: candidate.poi_id
      })
      get().applyAdjustment(response)
      set({ loading: false })
      return response
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : "替换失败"
      })
      return null
    }
  }
}))

import { create } from "zustand"

import { adjustPlan } from "../api/chat"
import { generatePlans } from "../api/plan"
import type { ChatResponse, ChatTurn } from "../types/chat"
import type { PlanRequest, RefinedPlan } from "../types/plan"

interface PlanStore {
  plans: RefinedPlan[]
  activePlanId: string | null
  loading: boolean
  error: string | null
  chatHistory: ChatTurn[]
  generatePlans: (params: PlanRequest) => Promise<void>
  switchPlan: (planId: string) => void
  applyAdjustment: (response: ChatResponse) => void
  sendAdjustment: (message: string) => Promise<void>
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
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : "方案生成失败"
      })
    }
  },
  switchPlan: planId => set({ activePlanId: planId }),
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
    if (!activePlanId) return
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
    } catch (error) {
      set({
        loading: false,
        error: error instanceof Error ? error.message : "调整失败"
      })
    }
  }
}))

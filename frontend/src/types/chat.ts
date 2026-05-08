import type { RefinedPlan } from "./plan"

export interface ChatTurn {
  role: "user" | "assistant"
  content: string
  timestamp: string
}

export interface ChatResponse {
  intent_type: string
  updated_plan?: RefinedPlan | null
  assistant_message: string
  requires_confirmation: boolean
  event_type?: string | null
  replan_level?: string | null
}

export interface ChatAdjustRequest {
  plan_id: string
  user_message: string
  chat_history: ChatTurn[]
  action_type?: string | null
  target_stop_index?: number | null
  replacement_poi_id?: string | null
}

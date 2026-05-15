export interface ChatTurn {
  role: "user" | "assistant"
  content: string
  timestamp: string
}

export interface ChatResponse {
  intent_type: string
  updated_plan?: unknown | null
  assistant_message: string
  requires_confirmation: boolean
  event_type?: string | null
  replan_level?: string | null
  recommended_poi_ids?: string[]
  alternative_poi_ids?: string[]
}

export interface ChatAdjustRequest {
  plan_id?: string | null
  pool_id?: string | null
  current_poi_ids?: string[]
  user_message: string
  chat_history: ChatTurn[]
  action_type?: string | null
  target_stop_index?: number | null
  replacement_poi_id?: string | null
  city?: string
  date?: string
  time_window?: {
    start: string
    end: string
  } | null
  free_text?: string | null
}

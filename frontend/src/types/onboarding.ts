export interface DestinationProfile {
  city: string
  start_location?: string | null
  target_area?: string | null
  end_location?: string | null
}

export interface TimeProfile {
  start_time?: string | null
  end_time?: string | null
  time_budget_minutes?: number | null
}

export interface BudgetProfile {
  budget_per_person?: number | null
  strict: boolean
}

export interface UserNeedProfile {
  user_id: string
  destination: DestinationProfile
  time: TimeProfile
  date: string
  activity_preferences: string[]
  food_preferences: string[]
  taste_preferences: string[]
  party_type?: string | null
  budget: BudgetProfile
  route_style: string[]
  avoid: string[]
  must_visit: string[]
  must_avoid: string[]
  completeness_score: number
  raw_query?: string | null
}

export interface OnboardingAnalyzeResponse {
  completeness_score: number
  missing_slots: string[]
  suggested_questions: string[]
  can_plan: boolean
  should_ask_followup: boolean
  extracted_profile: UserNeedProfile
}

export interface OnboardingProfileResponse {
  profile: UserNeedProfile
}

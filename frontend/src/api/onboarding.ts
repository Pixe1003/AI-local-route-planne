import { apiClient } from "./client"
import type { OnboardingAnalyzeResponse, OnboardingProfileResponse } from "../types/onboarding"

export async function analyzeOnboarding(query: string): Promise<OnboardingAnalyzeResponse> {
  return apiClient.post<OnboardingAnalyzeResponse, OnboardingAnalyzeResponse>("/onboarding/analyze", {
    query
  })
}

export async function buildNeedProfile(
  query: string,
  answers: Record<string, unknown>
): Promise<OnboardingProfileResponse> {
  return apiClient.post<OnboardingProfileResponse, OnboardingProfileResponse>("/onboarding/profile", {
    query,
    answers
  })
}

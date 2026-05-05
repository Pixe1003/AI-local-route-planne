import { create } from "zustand"

import type { UserNeedProfile } from "../types/onboarding"

interface UserStore {
  userId: string
  personaTags: string[]
  paceStyle: string
  needProfile: UserNeedProfile | null
  setPersonaTags: (tags: string[]) => void
  setPaceStyle: (style: string) => void
  setNeedProfile: (profile: UserNeedProfile) => void
}

export const useUserStore = create<UserStore>(set => ({
  userId: "mock_user",
  personaTags: ["couple", "foodie"],
  paceStyle: "balanced",
  needProfile: null,
  setPersonaTags: tags => set({ personaTags: tags }),
  setPaceStyle: style => set({ paceStyle: style }),
  setNeedProfile: profile => set({ needProfile: profile })
}))

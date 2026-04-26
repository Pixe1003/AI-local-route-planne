import { create } from "zustand"

interface UserStore {
  userId: string
  personaTags: string[]
  paceStyle: string
  setPersonaTags: (tags: string[]) => void
  setPaceStyle: (style: string) => void
}

export const useUserStore = create<UserStore>(set => ({
  userId: "mock_user",
  personaTags: ["couple", "foodie"],
  paceStyle: "balanced",
  setPersonaTags: tags => set({ personaTags: tags }),
  setPaceStyle: style => set({ paceStyle: style })
}))

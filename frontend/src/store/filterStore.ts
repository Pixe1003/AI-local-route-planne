import { create } from "zustand"

interface FilterState {
  category: string
  maxPrice: number
  maxQueue: number
  minRating: number
  radiusMeters: number
  setCategory: (category: string) => void
  setMaxPrice: (maxPrice: number) => void
  setMaxQueue: (maxQueue: number) => void
  setMinRating: (minRating: number) => void
  setRadiusMeters: (radiusMeters: number) => void
  reset: () => void
}

const defaults = {
  category: "all",
  maxPrice: 260,
  maxQueue: 45,
  minRating: 4.0,
  radiusMeters: 8000
}

export const useFilterStore = create<FilterState>(set => ({
  ...defaults,
  setCategory: category => set({ category }),
  setMaxPrice: maxPrice => set({ maxPrice }),
  setMaxQueue: maxQueue => set({ maxQueue }),
  setMinRating: minRating => set({ minRating }),
  setRadiusMeters: radiusMeters => set({ radiusMeters }),
  reset: () => set(defaults)
}))

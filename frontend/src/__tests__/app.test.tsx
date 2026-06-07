import { render } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import App from "../App"
import { usePreferenceStore } from "../store/preferenceStore"

vi.mock("../api/ugc", () => ({
  fetchUgcFeed: vi.fn().mockResolvedValue([])
}))

vi.mock("../api/agent", () => ({
  fetchUserFacts: vi.fn().mockResolvedValue({
    user_id: "mock_user",
    typical_budget_range: [80, 180],
    typical_party_type: "friends",
    typical_time_windows: [],
    favorite_districts: ["包河", "蜀山"],
    favorite_categories: ["restaurant", "culture"],
    avoid_categories: [],
    rejected_poi_ids: [],
    session_count: 2,
    updated_at: "2026-06-07T10:00:00Z"
  })
}))

vi.mock("../api/health", () => ({
  fetchSystemHealth: vi.fn().mockResolvedValue(null)
}))

describe("App", () => {
  beforeEach(() => {
    window.localStorage.clear()
    usePreferenceStore.setState({
      likedPoiIds: [],
      likedItems: {},
      snapshot: null,
      loading: false,
      error: null
    })
    window.history.pushState({}, "", "/")
  })

  it("renders the migrated discovery workstation as the first screen", async () => {
    const { container } = render(<App />)

    expect(container.querySelector(".app-layout")).toBeInTheDocument()
    expect(container.querySelector(".side-nav")).toBeInTheDocument()
    expect(container.querySelector(".app-topbar")).toBeInTheDocument()
    expect(container.querySelector(".discover-shell")).toBeInTheDocument()
    expect(container.querySelector(".service-workbench")).toBeInTheDocument()
    expect(container.querySelector(".plan-basket")).toBeInTheDocument()
  })

  it("renders favorites from persisted liked POIs", async () => {
    window.history.pushState({}, "", "/favorites")
    window.localStorage.setItem("airoute.likes", JSON.stringify(["poi_1"]))
    window.localStorage.setItem(
      "airoute.likedItems",
      JSON.stringify({
        poi_1: {
          post_id: "ugc_1",
          poi_id: "poi_1",
          poi_name: "天鹅湖夜景",
          title: "夜风刚好",
          source: "simulated_ugc",
          author: "本地体验官",
          cover_image: null,
          quote: "晚上散步很舒服。",
          tags: ["夜景", "散步"],
          category: "outdoor",
          rating: 4.8,
          price_per_person: 0,
          estimated_queue_min: 0,
          city: "hefei"
        }
      })
    )
    usePreferenceStore.setState({
      likedPoiIds: ["poi_1"],
      likedItems: {
        poi_1: {
          post_id: "ugc_1",
          poi_id: "poi_1",
          poi_name: "天鹅湖夜景",
          title: "夜风刚好",
          source: "simulated_ugc",
          author: "本地体验官",
          cover_image: null,
          quote: "晚上散步很舒服。",
          tags: ["夜景", "散步"],
          category: "outdoor",
          rating: 4.8,
          price_per_person: 0,
          estimated_queue_min: 0,
          city: "hefei"
        }
      },
      snapshot: null,
      loading: false,
      error: null
    })

    const { container } = render(<App />)

    expect(container.querySelector(".favorites-page")).toBeInTheDocument()
    expect(container.querySelector(".favorites-service-shell")).toBeInTheDocument()
    expect(container.textContent).toContain("天鹅湖夜景")
    expect(container.textContent).toContain("Agent 偏好记忆")
  })

  it("retires legacy planning routes back to discovery", async () => {
    window.history.pushState({}, "", "/plan")

    const { container } = render(<App />)

    expect(container.querySelector(".discovery-workspace")).toBeInTheDocument()
    expect(window.location.pathname).toBe("/")
  })

  it("retires legacy trip routes back to discovery", async () => {
    window.history.pushState({}, "", "/trips")

    const { container } = render(<App />)

    expect(container.querySelector(".discovery-workspace")).toBeInTheDocument()
    expect(window.location.pathname).toBe("/")
  })

  it("renders the project review H5 route", async () => {
    window.history.pushState({}, "", "/review")

    const { container } = render(<App />)

    expect(container.querySelector(".project-review-page")).toBeInTheDocument()
    expect(container.textContent).toContain("AIroute 项目复盘")
    expect(container.textContent).toContain("硬约束满足率")
  })

  it("explains the detailed agent workflow with code references", async () => {
    window.history.pushState({}, "", "/review")

    const { container } = render(<App />)

    expect(container.textContent).toContain("端到端交互链路")
    expect(container.textContent).toContain("Agent 内部框架")
    expect(container.textContent).toContain("技术选型")
    expect(container.textContent).toContain("ToolRegistry")
    expect(container.textContent).toContain("backend/app/agent/conductor.py")
    expect(container.textContent).toContain("frontend/src/pages/DiscoveryFeedPage.tsx")
    expect(container.textContent).toContain("OR-Tools CP-SAT")
  })

  it("renders a visual system interaction diagram", async () => {
    window.history.pushState({}, "", "/review")

    const { container } = render(<App />)

    expect(container.querySelector(".review-interaction-map")).toBeInTheDocument()
    expect(container.querySelectorAll(".interaction-node")).toHaveLength(8)
    expect(container.textContent).toContain("系统交互图")
    expect(container.textContent).toContain("用户反馈")
    expect(container.textContent).toContain("评测与可观测")
  })
})

import { fireEvent, render, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  syncSnapshot: vi.fn(),
  runAgentRoute: vi.fn(),
  fetchPool: vi.fn(),
  setNeedProfile: vi.fn(),
  setRouteRequest: vi.fn()
}))

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom")
  return {
    ...actual,
    useNavigate: () => mocks.navigate
  }
})

vi.mock("../api/ugc", () => ({
  fetchUgcFeed: vi.fn().mockResolvedValue([])
}))

vi.mock("../api/agent", () => ({
  runAgentRoute: (payload: unknown) => mocks.runAgentRoute(payload)
}))

vi.mock("../store/preferenceStore", () => ({
  usePreferenceStore: () => ({
    likedPoiIds: [],
    isLiked: () => false,
    toggleLike: vi.fn(),
    syncSnapshot: mocks.syncSnapshot,
    loading: false
  })
}))

vi.mock("../store/poolStore", () => ({
  usePoolStore: () => ({
    fetchPool: mocks.fetchPool,
    loading: false,
    error: null
  })
}))

vi.mock("../store/userStore", () => ({
  useUserStore: () => ({
    userId: "mock_user",
    setNeedProfile: mocks.setNeedProfile
  })
}))

vi.mock("../store/amapRouteStore", () => ({
  useAmapRouteStore: () => ({
    setRouteRequest: mocks.setRouteRequest
  })
}))

import { DiscoveryFeedPage } from "../pages/DiscoveryFeedPage"

describe("DiscoveryFeedPage Amap route flow", () => {
  it("keeps UGC onboarding but routes generation through the Amap route page", async () => {
    mocks.syncSnapshot.mockResolvedValue({
      user_id: "mock_user",
      city: "shanghai",
      liked_poi_ids: [],
      disliked_poi_ids: [],
      category_weights: {},
      tag_weights: {},
      budget_range: null,
      updated_at: "2026-05-10T00:00:00Z"
    })
    mocks.runAgentRoute.mockResolvedValue({
      session_id: "agent_session_1",
      trace_id: "trace_1",
      phase: "DONE",
      ordered_poi_ids: ["sh_poi_001", "sh_poi_002", "sh_poi_003"],
      route_chain: null,
      pool: {
        pool_id: "pool_1",
        categories: [],
        default_selected_ids: ["sh_poi_001", "sh_poi_002", "sh_poi_003"],
        meta: {
          total_count: 3,
          generated_at: "2026-05-10T00:00:00Z",
          user_persona_summary: "demo"
        }
      },
      steps: []
    })
    mocks.fetchPool.mockResolvedValue({
      pool_id: "pool_1",
      categories: [],
      default_selected_ids: ["sh_poi_001", "sh_poi_002", "sh_poi_003"],
      meta: {
        total_count: 3,
        generated_at: "2026-05-10T00:00:00Z",
        user_persona_summary: "demo"
      }
    })

    const { container } = render(<DiscoveryFeedPage />)

    fireEvent.click(container.querySelector(".instant-cta .primary-button") as HTMLButtonElement)
    fireEvent.submit(container.querySelector(".instant-panel") as HTMLFormElement)

    await waitFor(() => {
      expect(mocks.runAgentRoute).toHaveBeenCalledWith(
        expect.objectContaining({
          user_id: "mock_user",
          city: "hefei",
          free_text: expect.stringContaining("少排队")
        })
      )
    })
    expect(mocks.fetchPool).not.toHaveBeenCalled()
    await waitFor(() => {
      expect(mocks.setRouteRequest).toHaveBeenCalledWith(
        expect.objectContaining({
          mode: "driving",
          poi_ids: ["sh_poi_001", "sh_poi_002", "sh_poi_003"],
          source: "ugc_instant_route",
          session_id: "agent_session_1"
        })
      )
    })
    expect(mocks.navigate).toHaveBeenCalledWith("/route-map")
  })
})

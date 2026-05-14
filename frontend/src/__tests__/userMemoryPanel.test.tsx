import { render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  fetchUserFacts: vi.fn()
}))

vi.mock("../api/agent", () => ({
  fetchUserFacts: (userId: string, forceRefresh?: boolean) => mocks.fetchUserFacts(userId, forceRefresh)
}))

import { UserMemoryPanel } from "../components/UserMemoryPanel"

describe("UserMemoryPanel", () => {
  beforeEach(() => {
    mocks.fetchUserFacts.mockReset()
  })

  it("renders compact user facts when memory exists", async () => {
    mocks.fetchUserFacts.mockResolvedValue({
      user_id: "mock_user",
      typical_budget_range: [120, 220],
      typical_party_type: "friends",
      typical_time_windows: ["weekday_evening"],
      favorite_districts: ["庐阳区"],
      favorite_categories: ["restaurant", "cafe"],
      avoid_categories: ["shopping"],
      rejected_poi_ids: ["hf_poi_061581"],
      session_count: 3,
      updated_at: "2026-05-14T10:00:00Z"
    })

    render(<UserMemoryPanel userId="mock_user" />)

    await waitFor(() => {
      expect(screen.getByText("Agent 已记住偏好")).toBeInTheDocument()
    })
    expect(screen.getByText("¥120-220")).toBeInTheDocument()
    expect(screen.getByText("restaurant / cafe")).toBeInTheDocument()
    expect(screen.getByText("避开 shopping")).toBeInTheDocument()
    expect(screen.getByText("3 次会话")).toBeInTheDocument()
  })

  it("does not render when no memory exists", async () => {
    mocks.fetchUserFacts.mockResolvedValue({
      user_id: "new_user",
      typical_budget_range: null,
      typical_party_type: null,
      typical_time_windows: [],
      favorite_districts: [],
      favorite_categories: [],
      avoid_categories: [],
      rejected_poi_ids: [],
      session_count: 0,
      updated_at: "2026-05-14T10:00:00Z"
    })

    const { container } = render(<UserMemoryPanel userId="new_user" />)

    await waitFor(() => {
      expect(mocks.fetchUserFacts).toHaveBeenCalledWith("new_user", undefined)
    })
    expect(container.querySelector(".user-memory-panel")).toBeNull()
  })
})

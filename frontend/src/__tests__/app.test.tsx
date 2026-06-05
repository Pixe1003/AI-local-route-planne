import { render } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import App from "../App"

vi.mock("../api/ugc", () => ({
  fetchUgcFeed: vi.fn().mockResolvedValue([])
}))

describe("App", () => {
  beforeEach(() => {
    window.localStorage.clear()
    window.history.pushState({}, "", "/")
  })

  it("renders the UGC discovery feed as the first screen", async () => {
    const { container } = render(<App />)

    expect(container.querySelector(".discovery-workspace")).toBeInTheDocument()
    expect(container.querySelector(".instant-cta .primary-button")).toBeInTheDocument()
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

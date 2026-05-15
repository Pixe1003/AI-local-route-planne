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
})

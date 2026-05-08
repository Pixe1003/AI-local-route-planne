import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import App from "../App"

vi.mock("../api/ugc", () => ({
  fetchUgcFeed: vi.fn().mockResolvedValue([])
}))

describe("App", () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it("renders the UGC discovery feed as the first screen", async () => {
    render(<App />)

    expect(screen.getByRole("heading", { name: "现在就出发" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /现在出发/ })).toBeInTheDocument()
    expect(screen.getByText(/收藏会模拟历史偏好/)).toBeInTheDocument()
  })
})

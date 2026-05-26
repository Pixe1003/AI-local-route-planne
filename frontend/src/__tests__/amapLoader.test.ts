import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const loaderMock = vi.hoisted(() => ({
  load: vi.fn()
}))

vi.mock("@amap/amap-jsapi-loader", () => ({
  default: loaderMock
}))

describe("amapLoader", () => {
  beforeEach(() => {
    vi.resetModules()
    vi.stubEnv("VITE_AMAP_JS_KEY", "test-js-key")
    vi.stubEnv("VITE_AMAP_SECURITY_JS_CODE", "test-security-code")
    loaderMock.load.mockReset()
    loaderMock.load.mockResolvedValue({})
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it("loads map controls and route planning plugins", async () => {
    const { loadAmap } = await import("../utils/amapLoader")

    await loadAmap()

    expect(loaderMock.load).toHaveBeenCalledWith(
      expect.objectContaining({
        plugins: expect.arrayContaining(["AMap.Scale", "AMap.ToolBar", "AMap.Driving", "AMap.Walking"])
      })
    )
  })
})

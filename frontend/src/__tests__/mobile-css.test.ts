import { readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const currentDir = dirname(fileURLToPath(import.meta.url))
const css = readFileSync(resolve(currentDir, "../styles/globals.css"), "utf-8")

describe("mobile layout contract", () => {
  it("keeps UGC onboarding and Amap route content usable on phone screens", () => {
    expect(css).toContain("@media (max-width: 760px)")
    expect(css).toContain(".instant-panel")
    expect(css).toContain(".amap-route-page")
    expect(css).toContain(".route-map-shell")
    expect(css).toContain("env(safe-area-inset-bottom)")
    expect(css).toContain(".route-feedback-form")
    expect(css).toContain(".route-poi-list")
    expect(css).toContain("grid-template-columns: 1fr")
  })
})

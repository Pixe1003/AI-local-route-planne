import { readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const currentDir = dirname(fileURLToPath(import.meta.url))
const css = readFileSync(resolve(currentDir, "../styles/globals.css"), "utf-8")

describe("mobile layout contract", () => {
  it("keeps primary actions and dense route content usable on phone screens", () => {
    expect(css).toContain("@media (max-width: 760px)")
    expect(css).toContain(".mobile-action-bar")
    expect(css).toContain("env(safe-area-inset-bottom)")
    expect(css).toContain("overflow-x: auto")
    expect(css).toContain(".chat-box")
    expect(css).toContain("position: sticky")
    expect(css).toContain("grid-template-columns: 1fr")
  })
})

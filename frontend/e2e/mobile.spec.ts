import { expect, test, devices } from "@playwright/test"

test.use({
  ...devices["iPhone 13"]
})

async function expectNoHorizontalOverflow(page: import("@playwright/test").Page) {
  const noHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth
  )
  expect(noHorizontalOverflow).toBeTruthy()
}

test("mobile UGC onboarding can open instant route controls without layout overflow", async ({ page }) => {
  await page.goto("/")

  await expect(page.locator(".discovery-workspace")).toBeVisible()
  await expect(page.locator(".ugc-card").first()).toBeVisible({ timeout: 15_000 })
  await expect(page.locator(".instant-cta button")).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: "e2e-artifacts/mobile-ugc-feed.png", fullPage: true })

  await page.locator(".instant-cta button").click()
  await expect(page.locator(".instant-panel")).toBeVisible()
  await expect(page.locator(".instant-panel textarea")).toBeVisible()
  await expect(page.locator(".instant-panel button[type='submit']")).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: "e2e-artifacts/mobile-instant-route.png", fullPage: true })
})

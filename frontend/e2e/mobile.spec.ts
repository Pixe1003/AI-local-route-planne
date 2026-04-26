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

test("mobile user can generate pool and route without layout overflow", async ({ page }) => {
  await page.goto("/")

  await expect(page.getByRole("heading", { name: "AI 本地路线智能规划" })).toBeVisible()
  await expect(page.locator(".mobile-action-bar")).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: "e2e-artifacts/mobile-home.png", fullPage: true })

  await page.getByRole("button", { name: /生成推荐池/ }).click()
  await expect(page.getByRole("heading", { name: "推荐池" })).toBeVisible()
  await expect(page.locator(".poi-card").first()).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: "e2e-artifacts/mobile-pool.png", fullPage: true })

  await page.getByRole("button", { name: /生成方案/ }).click()
  await expect(page.locator(".plan-tabs")).toBeVisible()
  await expect(page.locator(".chat-box")).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: "e2e-artifacts/mobile-plan.png", fullPage: true })
})

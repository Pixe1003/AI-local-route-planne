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
  await expect(page.locator(".service-workbench")).toBeVisible()
  await expect(page.locator(".plan-basket")).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: "e2e-artifacts/mobile-service-workbench.png", fullPage: true })

  await expect(page.locator(".plan-basket-form")).toBeVisible()
  await expect(page.locator(".plan-basket-form textarea")).toBeVisible()
  await expect(page.locator(".plan-basket-form button[type='submit']")).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: "e2e-artifacts/mobile-plan-form.png", fullPage: true })
})

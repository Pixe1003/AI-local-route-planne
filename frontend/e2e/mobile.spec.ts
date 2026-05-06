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

test("mobile user can create a trip, save a route version, and open details without layout overflow", async ({ page }) => {
  await page.goto("/")

  await expect(page.getByRole("heading", { name: "我的行程" })).toBeVisible()
  await page.getByRole("button", { name: "新建行程" }).click()

  await expect(page.getByRole("heading", { name: "新建行程" })).toBeVisible()
  await expect(page.getByRole("button", { name: /进入推荐池/ })).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: "e2e-artifacts/mobile-trip-create.png", fullPage: true })

  await page.getByRole("button", { name: /进入推荐池/ }).click()
  await expect(page.getByRole("heading", { name: "推荐池" })).toBeVisible()
  await expect(page.locator(".poi-card").first()).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: "e2e-artifacts/mobile-pool.png", fullPage: true })

  await page.getByRole("button", { name: /生成并保存方案/ }).click()
  await expect(page.locator(".plan-tabs")).toBeVisible()
  await expect(page.locator(".chat-box")).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: "e2e-artifacts/mobile-plan.png", fullPage: true })

  await page.getByRole("button", { name: "行程详情" }).click()
  await expect(page.getByRole("heading", { name: /上海/ })).toBeVisible()
  await expect(page.getByRole("heading", { name: "版本历史" })).toBeVisible()
  await expectNoHorizontalOverflow(page)
  await page.screenshot({ path: "e2e-artifacts/mobile-trip-detail.png", fullPage: true })
})

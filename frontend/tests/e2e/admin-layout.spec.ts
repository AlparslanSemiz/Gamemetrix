import { expect, test } from '@playwright/test'


test('admin layout uses the available width on wide screens', async ({ page }) => {
  await page.setViewportSize({ width: 2560, height: 1200 })
  await page.route('**/api/auth/token', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ access_token: 'test-admin-token', token_type: 'bearer' }),
  }))

  const sessionLoaded = page.waitForResponse(
    (response) => response.url().endsWith('/api/account/session'),
  )
  await page.goto('/admin')
  await sessionLoaded
  await page.getByLabel('Username').fill('admin')
  await page.getByLabel('Password').fill('test-password')
  await page.getByRole('button', { name: 'Sign in' }).click()

  const layout = page.locator('.admin-layout')
  await expect(layout).toBeVisible()
  const rightGap = await layout.evaluate(
    (element) => window.innerWidth - element.getBoundingClientRect().right,
  )

  expect(rightGap).toBeLessThanOrEqual(32)
})

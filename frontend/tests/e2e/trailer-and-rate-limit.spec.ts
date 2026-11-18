import { expect, test, type Page } from '@playwright/test'

async function gotoHydrated(page: Page, path: string) {
  const sessionLoaded = page.waitForResponse((response) => response.url().endsWith('/api/account/session'))
  await page.goto(path)
  await sessionLoaded
  await expect(page.locator('[data-game-slug="complete-test-game"]')).toBeVisible()
}

test('trailer modal opens, plays the right video and closes', async ({ page }) => {
  await gotoHydrated(page, '/')
  await page.locator('[data-game-slug="catalog-test-game-2"] .cover, [data-game-slug="catalog-test-game-2"] .compact-cover').first().click()
  const dialog = page.getByRole('dialog', { name: /Catalog Test Game 2 trailer/ })
  await expect(dialog).toBeVisible()
  await expect(dialog.locator('iframe')).toHaveAttribute('src', /fastvideo2/)
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
})

test('a slow trailer for an earlier game never replaces the one opened last', async ({ page }) => {
  await gotoHydrated(page, '/')
  // complete-test-game answers after 800 ms; catalog-test-game-2 answers at once.
  await page.locator('[data-game-slug="complete-test-game"] .cover, [data-game-slug="complete-test-game"] .compact-cover').first().click()
  await expect(page.getByRole('dialog', { name: /Complete Test Game trailer/ })).toBeVisible()
  await page.keyboard.press('Escape')
  await page.locator('[data-game-slug="catalog-test-game-2"] .cover, [data-game-slug="catalog-test-game-2"] .compact-cover').first().click()

  const dialog = page.getByRole('dialog', { name: /Catalog Test Game 2 trailer/ })
  await expect(dialog.locator('iframe')).toHaveAttribute('src', /fastvideo2/)
  await page.waitForTimeout(1200)
  await expect(dialog.locator('iframe')).toHaveAttribute('src', /fastvideo2/)
  await expect(page.locator('iframe[src*="slowvideo01"]')).toHaveCount(0)
})

test('closing the modal while a trailer loads leaves it closed', async ({ page }) => {
  await gotoHydrated(page, '/')
  await page.locator('[data-game-slug="complete-test-game"] .cover, [data-game-slug="complete-test-game"] .compact-cover').first().click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.keyboard.press('Escape')
  await page.waitForTimeout(1200)
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.locator('iframe')).toHaveCount(0)
})

test('a rate-limited backend shows a retry screen, not an empty catalog', async ({ page }) => {
  const response = await page.goto('/?developer=__catalog_rate_limited__')
  expect(response?.status()).toBe(429)
  expect(response?.headers()['retry-after']).toBe('7')
  expect(response?.headers()['cache-control']).toContain('no-store')
  await expect(page.getByRole('heading', { name: 'Busy right now, please try again in a moment' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible()
  await expect(page.locator('[data-game-slug]')).toHaveCount(0)
})

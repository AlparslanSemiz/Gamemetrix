import { expect, test, type Page } from '@playwright/test'

// The server renders in the container's zone and locale; browsers differ. A
// date or number formatted from the local zone or locale makes the two disagree
// (React #418) and shifts calendar days. Run the public pages in zones on both
// sides of UTC and in a locale with different number formatting.
const HYDRATION_ERROR = /hydrat|did not match|server rendered|react\.dev\/errors\/(418|419|422|423|425)|Minified React error #(418|419|422|423|425)/i

const ZONES = [
  { timezoneId: 'America/Los_Angeles', locale: 'de-DE' },
  { timezoneId: 'Pacific/Auckland', locale: 'en-NZ' },
  { timezoneId: 'Asia/Kolkata', locale: 'tr-TR' },
] as const

const PAGES = [
  { path: '/game/complete-test-game', ready: '.dp-score-block' },
  { path: '/best/linux-games', ready: '.curated-list' },
  { path: '/deals', ready: '.curated-list' },
  { path: '/best/games/2024', ready: '.curated-list' },
  { path: '/', ready: '[data-game-slug="complete-test-game"]' },
] as const

function trackHydrationErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error' && HYDRATION_ERROR.test(message.text())) errors.push(message.text())
  })
  page.on('pageerror', (error) => {
    if (HYDRATION_ERROR.test(error.message)) errors.push(error.message)
  })
  return errors
}

for (const zone of ZONES) {
  test.describe(`hydration in ${zone.timezoneId} / ${zone.locale}`, () => {
    test.use({ timezoneId: zone.timezoneId, locale: zone.locale })

    for (const { path, ready } of PAGES) {
      test(`${path} hydrates cleanly`, async ({ page }) => {
        const errors = trackHydrationErrors(page)
        await page.goto(path)
        await expect(page.locator(ready).first()).toBeVisible()
        // Let hydration, effects and the first client re-render settle.
        await page.waitForLoadState('networkidle')
        expect(errors, errors.join('\n')).toEqual([])
      })
    }

    test('release date is the calendar day in the data, not the visitor day', async ({ page }) => {
      await page.goto('/game/complete-test-game')
      await expect(page.locator('.dp-score-block')).toBeVisible()
      // The fixture releases on 2024-04-12 (UTC midnight): west of UTC the local
      // day is the 11th, so a local-zone formatter shows the wrong date.
      await expect(page.getByText('Apr 12, 2024').first()).toBeVisible()
      await expect(page.getByText('Apr 11, 2024')).toHaveCount(0)
    })

    test('counts keep en-US grouping regardless of locale', async ({ page }) => {
      await page.goto('/game/complete-test-game')
      await expect(page.getByText('25,000').first()).toBeVisible()
    })
  })
}

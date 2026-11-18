import { expect, test } from '@playwright/test'

// A 390px phone must never scroll sideways: the curated header (search + Login) and
// the fixed analytics banner both used to push the document to 414px.
const PAGES = ['/', '/deals', '/best/linux-games', '/best/games/2024', '/about', '/game/complete-test-game'] as const

test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true })

for (const path of PAGES) {
  test(`no horizontal overflow at 390px on ${path}`, async ({ page }) => {
    const sessionLoaded = page.waitForResponse((response) => response.url().endsWith('/api/account/session'))
    await page.goto(path)
    await sessionLoaded
    await expect(page.locator('#main-content')).toBeVisible()
    await page.waitForTimeout(300)

    const widths = await page.evaluate(() => ({
      document: document.documentElement.scrollWidth,
      body: document.body.scrollWidth,
      viewport: window.innerWidth,
    }))
    expect(widths.viewport).toBe(390)
    expect(widths.document, `document scrollWidth on ${path}`).toBeLessThanOrEqual(390)
    expect(widths.body, `body scrollWidth on ${path}`).toBeLessThanOrEqual(390)

    const banner = page.locator('aside.analytics-consent')
    if (await banner.count()) {
      const box = await banner.boundingBox()
      expect(box).not.toBeNull()
      expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(390)
    }
  })
}

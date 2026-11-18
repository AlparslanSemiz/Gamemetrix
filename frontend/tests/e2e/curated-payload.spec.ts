import { expect, test } from '@playwright/test'

// Ranking pages render 100 rows. The loader projects each backend row down to
// the fields the row shows (src/utils/curatedCards.ts); before that, the full
// catalog payload (price history, per-source detail text, summaries) went into
// the HTML as hydration data: ~236 KB per page against the mock rows, 324 KB
// on the live /best/linux-games. The mock API returns 100 production-shaped rows.
const PAGES = ['/best/linux-games', '/best/steam-deck-games', '/best/rpg-games', '/best/games/2024', '/deals'] as const
const HYDRATION_BUDGET_BYTES = 80_000
const HTML_BUDGET_BYTES = 360_000

function hydrationBytes(html: string): number {
  return [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)]
    .map((match) => match[1])
    .filter((body) => body.includes('__reactRouterContext') || body.includes('streamController'))
    .reduce((total, body) => total + Buffer.byteLength(body), 0)
}

for (const path of PAGES) {
  test(`${path} ships only the row fields as loader data`, async ({ request }) => {
    const response = await request.get(path)
    expect(response.status()).toBe(200)
    const html = await response.text()

    expect(hydrationBytes(html), 'serialized loader data').toBeLessThan(HYDRATION_BUDGET_BYTES)
    expect(Buffer.byteLength(html), 'whole document').toBeLessThan(HTML_BUDGET_BYTES)
    for (const field of ['price_snapshots', 'summary_short', 'fetched_at', 'applicable_sources', 'hltb_url']) {
      expect(html, `${field} must not reach the page`).not.toContain(field)
    }

    // SEO content stays complete: all 100 rows and a 100-item ItemList.
    expect(html.match(/<li><span class="curated-rank">/g)?.length).toBe(100)
    const jsonLd = html.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/)?.[1] ?? ''
    expect(jsonLd).toContain('"numberOfItems":100')
    expect(jsonLd).toContain('https://gamemetrix.me/game/ranked-fixture-game-100')
  })
}

test('ranking rows still show scores, price and store link after hydration', async ({ page }) => {
  await page.goto('/best/linux-games')
  const first = page.locator('.curated-list > li').first()
  await expect(first.locator('.curated-game-head strong')).toHaveText('88')
  await expect(first.locator('.curated-scores b')).toHaveText(['88', '89', '87', '88'])
  await expect(first.locator('.curated-context')).toContainText('Linux: Gold')
  await expect(first.locator('.curated-context')).toContainText('30h HLTB')
  await expect(first.locator('.curated-context')).toContainText('$29.99 · 50% off')
  await expect(first.getByRole('link', { name: 'Store' })).toHaveAttribute('href', 'https://store.steampowered.com/')
  // RAWG covers come from the 420 px variant, not the multi-megapixel original.
  await expect(page.locator('.curated-list > li').nth(99).locator('.curated-cover img'))
    .toHaveAttribute('src', 'https://media.rawg.io/media/resize/420/-/games/f99/fixture-cover-99.jpg')
})

import { expect, test } from '@playwright/test'

const DETAIL_URL = '/game/complete-test-game'

test('detail page hydrates without server/client mismatches', async ({ page }) => {
  const errors: string[] = []
  page.on('console', (msg) => { if (msg.type() === 'error') errors.push(msg.text()) })
  page.on('pageerror', (err) => errors.push(err.message))

  await page.goto(DETAIL_URL)
  await expect(page.locator('.dp-score-block')).toBeVisible()

  const hydration = errors.filter((e) => /hydrat|did not match|server rendered/i.test(e))
  expect(hydration, hydration.join('\n')).toHaveLength(0)
})

test('collection actions toggle and persist into shared state', async ({ page }) => {
  await page.goto(DETAIL_URL)

  await expect(page.getByRole('button', { name: /Add to my games/i })).toBeVisible()
  await page.getByRole('button', { name: /Add to wishlist/i }).click()
  await expect(page.getByRole('button', { name: /On wishlist/i })).toBeVisible()

  const menuButton = page.getByRole('button', { name: /Save to collection/i })
  await menuButton.click()
  const playing = page.getByRole('menuitemcheckbox', { name: /Currently playing/i })
  // The menu must paint above the score block, which owns a backdrop-filter
  // stacking context directly beneath it.
  await expect(playing).toBeInViewport()
  await playing.click()
  await expect(playing).toHaveAttribute('aria-checked', 'true')

  await page.reload()
  await expect(page.getByRole('button', { name: /On wishlist/i })).toBeVisible()
})

test('score signals appear once, not duplicated in the info table', async ({ page }) => {
  await page.goto(DETAIL_URL)

  const stats = page.locator('.dp-score-stats')
  await expect(stats).toContainText('Popularity')
  await expect(stats).toContainText('Ranking')
  await expect(page.locator('.dp-signal-grid')).toHaveCount(0)
  await expect(page.locator('.dp-info-key', { hasText: /^Popularity$/ })).toHaveCount(0)
})

test('price panel lives in the right column beside the gallery', async ({ page }) => {
  await page.goto(DETAIL_URL)
  await expect(page.locator('.dp-right .dp-price-panel')).toHaveCount(1)
  await expect(page.locator('.dp-left .dp-price-panel')).toHaveCount(0)
})

test('DLCs live below where to buy in the right column', async ({ page }) => {
  await page.goto(DETAIL_URL)

  const pricePanel = page.locator('.dp-right .dp-price-panel')
  const dlcSection = page.locator('.dp-right .dp-dlc-section')
  await expect(dlcSection).toHaveCount(1)
  await expect(page.locator('.dp-bottom-related .dp-dlc-section')).toHaveCount(0)

  const priceBox = await pricePanel.boundingBox()
  const dlcBox = await dlcSection.boundingBox()
  expect(priceBox).not.toBeNull()
  expect(dlcBox).not.toBeNull()
  expect(dlcBox!.y).toBeGreaterThan(priceBox!.y + priceBox!.height)
})

test('gallery preview shows ten tiles across five rows', async ({ page }) => {
  await page.goto(DETAIL_URL)

  const tiles = page.locator('.dp-gallery-rest .dp-gallery-img')
  await expect(tiles).toHaveCount(10)

  const boxes = await tiles.evaluateAll((elements) => elements.map((element) => {
    const { x, y } = element.getBoundingClientRect()
    return { x: Math.round(x), y: Math.round(y) }
  }))
  expect(new Set(boxes.map(({ y }) => y)).size).toBe(5)
  for (let index = 0; index < boxes.length; index += 2) {
    expect(boxes[index].y).toBe(boxes[index + 1].y)
    expect(boxes[index].x).toBeLessThan(boxes[index + 1].x)
  }
})

test('gallery requests scaled thumbnails, never full-size originals', async ({ page }) => {
  await page.goto(DETAIL_URL)

  const thumbs = page.locator('.dp-gallery-rest img, .dp-gallery-strip-item img')
  const count = await thumbs.count()
  for (let i = 0; i < count; i += 1) {
    const src = await thumbs.nth(i).getAttribute('src')
    expect(src, 'thumbnails must not load the 1920x1080 Steam original').not.toContain('.1920x1080.')
    if (src?.includes('media.rawg.io/media/')) {
      expect(src, 'RAWG thumbnails must use a resize variant').toContain('/resize/')
    }
  }
})

test('mobile stacks the media column below the page content', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(DETAIL_URL)

  const title = await page.locator('.dp-title').boundingBox()
  const gallery = await page.locator('.dp-gallery-panel').boundingBox()
  expect(title!.y).toBeLessThan(gallery!.y)
  // Single-column info table: one track, so no space in the computed value.
  await expect(page.locator('.dp-info-table')).toHaveCSS('grid-template-columns', /^\d+(\.\d+)?px$/)
})

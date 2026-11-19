import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

// The hero <img> has a RAWG srcset (420/640/1280). On a narrow 1x screen the
// browser fetches the 420w file, so a near-square real cover decodes at 420 px
// wide; that must not trip the "small near-square = placeholder" heuristic.
test.use({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 })

function svg(width: number, height: number) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="${width}" height="${height}" fill="#345"/></svg>`
}

async function serveCovers(page: Page) {
  // Delay the art so it decodes after hydration and React sees the load event.
  await page.route('https://media.rawg.io/**', async (route) => {
    const width = Number(route.request().url().match(/\/resize\/(\d+)\//)?.[1] ?? 900)
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 700))
    await route.fulfill({ contentType: 'image/svg+xml', body: svg(width, Math.round(width * 1.19)) })
  })
  await page.route('https://images.example/**', async (route) => {
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 700))
    await route.fulfill({ contentType: 'image/svg+xml', body: svg(300, 300) })
  })
}

async function heroLoaded(page: Page) {
  const hero = page.locator('.dp-gallery-hero')
  await expect(hero).toBeVisible()
  await page.waitForFunction(() => {
    const image = document.querySelector<HTMLImageElement>('.dp-gallery-hero')
    return Boolean(image?.complete && image.naturalWidth > 0)
  })
  // Let React commit any fallback swap triggered by onLoad.
  await page.evaluate(() => new Promise((resolveFrame) => requestAnimationFrame(() => requestAnimationFrame(resolveFrame))))
  return hero
}

test('a near-square RAWG cover served at 420 px stays the hero on a narrow screen', async ({ page }) => {
  await serveCovers(page)
  await page.goto('/game/rawg-square-cover-game')
  const hero = await heroLoaded(page)
  const loaded = await hero.evaluate((image: HTMLImageElement) => ({
    currentSrc: image.currentSrc,
    naturalWidth: image.naturalWidth,
    naturalHeight: image.naturalHeight,
  }))
  expect(loaded.currentSrc).toBe('https://media.rawg.io/media/resize/420/-/games/sq1/square-cover.jpg')
  // naturalWidth is density-corrected for srcset picks (420w in a 390 px slot -> 390).
  expect(loaded.naturalWidth).toBeLessThan(600)
  expect(loaded.naturalWidth / loaded.naturalHeight).toBeGreaterThan(0.8)
  await expect(hero).toHaveAttribute('src', 'https://media.rawg.io/media/resize/1280/-/games/sq1/square-cover.jpg')
  await expect(hero).toHaveAttribute('srcset', /resize\/420\/-\/games\/sq1\/square-cover\.jpg 420w/)
})

test('an original-size small square logo is still swapped for a screenshot', async ({ page }) => {
  await serveCovers(page)
  await page.goto('/game/small-logo-cover-game')
  const hero = page.locator('.dp-gallery-hero')
  await expect(hero).toHaveAttribute('src', 'http://127.0.0.1:4173/favicon.svg?screenshot=1')
  await expect(hero).not.toHaveAttribute('srcset', /./)
})

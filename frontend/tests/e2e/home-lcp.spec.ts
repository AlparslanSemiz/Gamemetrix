import { expect, test } from '@playwright/test'

// The home LCP element is the first card's cover. It must paint from the server HTML
// alone: no lazy loading, no hidden/fade-in state that only hydration lifts. If JS ever
// gates it, every visitor's LCP includes the whole module graph.
test.describe('home LCP cover without JavaScript', () => {
  test.use({ javaScriptEnabled: false })

  test('first card cover is eager, preloaded, loaded and visible', async ({ page }) => {
    await page.goto('/')
    const cover = page.locator('.game-list article').first().locator('img').first()
    await expect(cover).toBeVisible()
    await expect(cover).toHaveAttribute('loading', 'eager')
    await expect(cover).toHaveAttribute('fetchpriority', 'high')
    await expect(cover).toBeInViewport()

    const src = await cover.getAttribute('src')
    expect(src).toBeTruthy()
    // React also hoists its own preload for an eager high-priority image, so expect one or more.
    expect(await page.locator(`head link[rel="preload"][as="image"][href="${src}"]`).count()).toBeGreaterThan(0)

    await expect.poll(() => cover.evaluate((image: HTMLImageElement) => image.complete && image.naturalWidth > 0)).toBe(true)
    const style = await cover.evaluate((image) => {
      let opacity = 1
      for (let node: Element | null = image; node; node = node.parentElement) {
        opacity *= Number(getComputedStyle(node).opacity)
      }
      const own = getComputedStyle(image)
      return { opacity, visibility: own.visibility, contentVisibility: own.contentVisibility }
    })
    expect(style).toEqual({ opacity: 1, visibility: 'visible', contentVisibility: 'visible' })
  })
})

// vite.config.ts groups the small shared app modules into one chunk. Split per module,
// the home page fetched 22 scripts in a four-level import chain (now 10), and Lighthouse's
// simulated LCP paid for every level.
test('home page loads a short module graph', async ({ page }) => {
  const scripts = new Set<string>()
  page.on('request', (request) => {
    if (request.resourceType() === 'script' && new URL(request.url()).pathname.startsWith('/assets/')) {
      scripts.add(new URL(request.url()).pathname)
    }
  })
  await page.goto('/', { waitUntil: 'networkidle' })
  await expect(page.locator('.game-list article').first()).toBeVisible()
  expect([...scripts].length, [...scripts].join('\n')).toBeLessThanOrEqual(12)
})

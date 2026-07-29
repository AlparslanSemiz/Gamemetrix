import { expect, test, type Page } from '@playwright/test'

async function gotoHydrated(page: Page, path: string) {
  const sessionLoaded = page.waitForResponse((response) =>
    response.url().endsWith('/api/account/session'),
  )
  await page.goto(path)
  await sessionLoaded
  await expect(page.locator('[data-game-slug="complete-test-game"]')).toBeVisible()
}

function isCatalogOrRouteData(url: string): boolean {
  const parsed = new URL(url)
  return (
    parsed.pathname.startsWith('/api/catalog/')
    || parsed.pathname.startsWith('/api/seo/curated/')
    || parsed.pathname.endsWith('.data')
  )
}

test('Home, Wishlist and For You switch locally within the 100 ms budget', async ({ page }) => {
  await gotoHydrated(page, '/')
  await page.waitForTimeout(300)
  const unexpectedRequests: string[] = []
  page.on('request', (request) => {
    if (isCatalogOrRouteData(request.url())) unexpectedRequests.push(request.url())
  })

  for (const [title, heading] of [
    ['For You', 'Discover'],
    ['Wishlist', 'Wishlist'],
    ['Home', 'Game scores and PC compatibility rankings'],
  ]) {
    const elapsed = await page.evaluate(async ({ buttonTitle, expectedHeading }) => {
      const button = document.querySelector<HTMLButtonElement>(
        `.side-rail button[title="${buttonTitle}"]`,
      )
      if (!button) throw new Error(`Missing ${buttonTitle} navigation button`)
      const startedAt = performance.now()
      return new Promise<number>((resolve, reject) => {
        const observer = new MutationObserver(() => {
          if (document.querySelector('h1')?.textContent !== expectedHeading) return
          observer.disconnect()
          resolve(performance.now() - startedAt)
        })
        observer.observe(document.body, { childList: true, subtree: true })
        button.click()
        if (document.querySelector('h1')?.textContent === expectedHeading) {
          observer.disconnect()
          resolve(performance.now() - startedAt)
        }
        window.setTimeout(() => {
          observer.disconnect()
          reject(new Error(`Timed out waiting for ${expectedHeading}`))
        }, 1_000)
      })
    }, { buttonTitle: title, expectedHeading: heading })
    expect(elapsed, `${title} should commit within budget`).toBeLessThanOrEqual(100)
  }

  await page.goBack()
  await expect(page.getByRole('heading', { name: 'Wishlist', exact: true })).toBeVisible()
  await page.goBack()
  await expect(page.getByRole('heading', { name: 'Discover', exact: true })).toBeVisible()
  expect(unexpectedRequests).toEqual([])
})

test('utility routes do not bootstrap or request a curated catalog', async ({ page }) => {
  await gotoHydrated(page, '/')
  await page.waitForTimeout(300)
  const catalogRequests: string[] = []
  page.on('request', (request) => {
    const pathname = new URL(request.url()).pathname
    if (
      pathname.startsWith('/api/catalog/')
      || pathname.startsWith('/api/seo/curated/')
    ) {
      catalogRequests.push(request.url())
    }
  })

  for (const title of ['Settings', 'Alerts', 'About']) {
    await page.getByTitle(title, { exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`/${title.toLowerCase()}$`))
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible()
  }

  expect(catalogRequests).toEqual([])
  await page.getByTitle('Home', { exact: true }).click()
  await expect(page.locator('[data-game-slug="complete-test-game"]')).toBeVisible()
  await expect(page.locator('.skeleton-card')).toHaveCount(0)
})

for (const viewport of [
  { name: 'desktop', width: 1280, height: 720, returnBudgetMs: 300 },
  { name: 'mobile', width: 390, height: 844, returnBudgetMs: 500 },
]) {
  test(`${viewport.name}: detail back restores filters, grid, pages and card position`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await gotoHydrated(page, '/')

    const filteredPage = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return (
        url.pathname === '/api/catalog/games'
        && url.searchParams.get('q') === 'Catalog'
        && url.searchParams.get('offset') === '0'
      )
    })
    await page.getByLabel('Search games by title').fill('Catalog')
    await filteredPage
    await expect(page.locator('.skeleton-card')).toHaveCount(0)
    await page.getByTitle('Grid view').click()
    await expect(page.locator('.game-list-grid')).toBeVisible()

    await page.locator('.scroll-sentinel').scrollIntoViewIfNeeded()
    await expect(page.getByRole('link', { name: 'Catalog Test Game 30', exact: true })).toBeVisible()
    const card = page.locator('[data-game-slug="catalog-test-game-30"]')
    await card.scrollIntoViewIfNeeded()
    const topBefore = await card.evaluate((element) => element.getBoundingClientRect().top)

    await page.evaluate(() => {
      const state = window as typeof window & {
        __gmSkeletonSeenAfterBack?: boolean
        __gmSkeletonObserver?: MutationObserver
      }
      state.__gmSkeletonSeenAfterBack = false
      state.__gmSkeletonObserver = new MutationObserver(() => {
        if (document.querySelector('.skeleton-card')) state.__gmSkeletonSeenAfterBack = true
      })
      state.__gmSkeletonObserver.observe(document.body, { childList: true, subtree: true })
    })

    await page.getByRole('link', { name: 'Catalog Test Game 30', exact: true }).click()
    await expect(page.locator('.dp-score-block')).toBeVisible()
    await page.evaluate(() => {
      const state = window as typeof window & {
        __gmBackPaintMs?: number
      }
      const startedAt = performance.now()
      const observer = new MutationObserver(() => {
        if (!document.querySelector('.app-shell')) return
        observer.disconnect()
        requestAnimationFrame(() => {
          state.__gmBackPaintMs = performance.now() - startedAt
        })
      })
      observer.observe(document.body, { childList: true, subtree: true })
      window.history.back()
    })
    await expect(page.locator('[data-game-slug="catalog-test-game-30"]')).toBeVisible()
    await expect.poll(() => page.evaluate(() => (
      window as typeof window & { __gmBackPaintMs?: number }
    ).__gmBackPaintMs)).not.toBeUndefined()
    const backPaintMs = await page.evaluate(() => (
      window as typeof window & { __gmBackPaintMs?: number }
    ).__gmBackPaintMs ?? Number.POSITIVE_INFINITY)
    expect(backPaintMs).toBeLessThanOrEqual(viewport.returnBudgetMs)

    await expect(page.getByLabel('Search games by title')).toHaveValue('Catalog')
    await expect(page.locator('.game-list-grid')).toBeVisible()
    await expect(page.locator('.skeleton-card')).toHaveCount(0)
    expect(await page.evaluate(() => (
      window as typeof window & { __gmSkeletonSeenAfterBack?: boolean }
    ).__gmSkeletonSeenAfterBack)).toBe(false)
    const topAfter = await card.evaluate((element) => element.getBoundingClientRect().top)
    expect(Math.abs(topAfter - topBefore)).toBeLessThanOrEqual(20)
  })
}

test('touch input still opens a prefetched detail route', async ({ browser }) => {
  const context = await browser.newContext({
    baseURL: 'http://127.0.0.1:4173',
    hasTouch: true,
    isMobile: true,
    viewport: { width: 390, height: 844 },
  })
  const page = await context.newPage()
  try {
    await gotoHydrated(page, '/')
    const link = page.getByRole('link', { name: 'Complete Test Game', exact: true })
    await expect(link).toBeVisible()
    await link.tap()
    await expect(page.locator('.dp-score-block')).toBeVisible()
  } finally {
    await context.close()
  }
})

for (const viewport of [
  { name: 'desktop', width: 1280, height: 720 },
  { name: 'mobile', width: 390, height: 844 },
]) {
  test(`${viewport.name}: related requests wait until their section is within 600 px`, async ({ page }) => {
    await page.setViewportSize(viewport)
    const relatedRequests: string[] = []
    page.on('request', (request) => {
      const pathname = new URL(request.url()).pathname
      if (pathname.endsWith('/similar') || pathname.endsWith('/series')) {
        relatedRequests.push(pathname)
      }
    })

    await page.goto('/game/complete-test-game')
    await expect(page.locator('.dp-score-block')).toBeVisible()
    await page.waitForTimeout(300)
    expect(relatedRequests).toEqual([])

    await page.locator('.dp-related-lazy').scrollIntoViewIfNeeded()
    await expect.poll(() => relatedRequests.filter((path) => path.endsWith('/similar')).length)
      .toBe(1)
    await expect.poll(() => relatedRequests.filter((path) => path.endsWith('/series')).length)
      .toBe(1)
  })
}

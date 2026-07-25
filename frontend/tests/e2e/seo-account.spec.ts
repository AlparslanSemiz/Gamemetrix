import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

async function gotoHydrated(page: Page, path: string) {
  const sessionLoaded = page.waitForResponse((response) => response.url().endsWith('/api/account/session'))
  await page.goto(path)
  await sessionLoaded
}

test('crawler receives complete game HTML without executing JavaScript', async ({ request }) => {
  const response = await request.get('/game/complete-test-game')
  expect(response.status()).toBe(200)
  const html = await response.text()
  expect(html).toMatch(/<h1[^>]*>Complete Test Game<\/h1>/)
  for (const source of ['Metacritic', 'OpenCritic', 'Steam', 'IGDB']) expect(html).toContain(source)
  expect(html).toContain('rel="canonical"')
  expect(html).toContain('name="description"')
  expect(html).toContain('application/ld+json')
  expect(html).toContain('ProtonDB')
  expect(html).toContain('Gold')

  expect((await request.get('/game/definitely-missing')).status()).toBe(404)
  expect((await request.get('/sitemap.xml')).headers()['content-type']).toContain('application/xml')
  expect((await request.get('/robots.txt')).headers()['content-type']).toContain('text/plain')
})

test('home SSR and infinite catalog use the same full-catalog total', async ({ request }) => {
  const response = await request.get('/')
  expect(response.status()).toBe(200)
  const html = await response.text()
  const visibleText = html
    .replaceAll('<!-- -->', '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')

  expect(visibleText).toContain('1 / 48 loaded')
  expect(visibleText).not.toContain('1 / 400 loaded')
})

test('a stalled catalog page can be retried without skipping it', async ({ page }) => {
  let offset24Requests = 0
  await page.route('**/api/games?**', async (route) => {
    const url = new URL(route.request().url())
    if (url.searchParams.get('offset') !== '24' || offset24Requests++ > 0) {
      await route.continue()
      return
    }

    await new Promise((resolve) => setTimeout(resolve, 1_500))
    await route.abort('timedout').catch(() => undefined)
  })

  await gotoHydrated(page, '/')
  await expect(page.getByText('Loading more…')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Retry loading games' })).toBeVisible()

  await page.getByRole('button', { name: 'Retry loading games' }).click()
  await expect(page.getByText('Catalog Test Game 25')).toBeVisible()
  expect(offset24Requests).toBe(2)
})

test('desktop and mobile navigation expose account controls without admin', async ({ page }) => {
  const hydrationErrors = []
  page.on('console', (message) => {
    if (message.type() === 'error' && /hydration/i.test(message.text())) hydrationErrors.push(message.text())
  })
  await gotoHydrated(page, '/')
  await expect(page.getByRole('heading', { name: 'Game rankings' })).toBeVisible()
  await expect(page.getByTitle('Login')).toBeVisible()
  await expect(page.getByTitle('Admin')).toHaveCount(0)
  expect(hydrationErrors).toEqual([])
  await page.screenshot({ path: 'test-results/home-desktop.png', fullPage: true })

  await page.setViewportSize({ width: 390, height: 844 })
  const mobileSessionLoaded = page.waitForResponse((response) => response.url().endsWith('/api/account/session'))
  await page.reload()
  await mobileSessionLoaded
  await page.getByRole('button', { name: 'More' }).click()
  const menu = page.locator('.mobile-more-menu')
  await expect(menu.getByText('Login')).toBeVisible()
  await expect(menu.getByText('Admin')).toHaveCount(0)
  const box = await menu.boundingBox()
  expect(box).not.toBeNull()
  expect((box?.x ?? -1) + (box?.width ?? 1000)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: 'test-results/home-mobile.png', fullPage: true })
})

test('utility panels have dedicated noindex routes and return to catalog navigation', async ({ page }) => {
  await gotoHydrated(page, '/')
  await page.getByTitle('Settings').click()
  await expect(page).toHaveURL(/\/settings$/)
  await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'noindex,follow')
  await expect(page.getByTitle('Login')).toBeVisible()
  await expect(page.getByTitle('Admin')).toHaveCount(0)

  await page.getByTitle('Home').click()
  await expect(page).toHaveURL('http://127.0.0.1:4173/')
  await expect(page.getByRole('heading', { name: 'Game rankings' })).toBeVisible()

  await page.getByRole('button', { name: 'Wishlist', exact: true }).click()
  await expect(page).toHaveURL(/\?view=watchlist$/)
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'noindex,follow')
})

test('login merges valid guest collections and changes Login to Account', async ({ page, request }) => {
  const hydrationErrors: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error' && /hydration/i.test(message.text())) hydrationErrors.push(message.text())
  })
  await gotoHydrated(page, '/')
  await page.evaluate(() => {
    localStorage.setItem('gamemetrix.collections', JSON.stringify({
      watchlist: ['complete-test-game', '../invalid'],
      playing: [], seen: [], completed: [], liked: [], favorites: [],
    }))
  })
  await gotoHydrated(page, '/login')
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByLabel('Email').fill('player@example.com')
  await page.getByLabel('Password').fill('correct horse battery staple')
  await page.getByRole('button', { name: 'Log in' }).click()
  await expect(page).toHaveURL(/\/account$/)
  await expect(page.getByRole('heading', { name: 'Test Player' })).toBeVisible()
  await expect(page.getByText('1 saved collection entries are synchronized.')).toBeVisible()

  const merge = await (await request.get('http://127.0.0.1:8001/__test/merge')).json()
  expect(merge.collections.watchlist).toEqual(['complete-test-game'])

  await gotoHydrated(page, '/')
  await expect(page.getByTitle('Account')).toBeVisible()
  await expect(page.getByTitle('Admin')).toHaveCount(0)
  const storedValues = await page.evaluate(() => [
    ...Object.values(localStorage),
    ...Object.values(sessionStorage),
  ])
  expect(storedValues.join(' ')).not.toContain('test-session')
  expect(storedValues.join(' ')).not.toContain('test-csrf')
  expect(hydrationErrors).toEqual([])
})

test('admin login remains directly accessible and excluded from indexing', async ({ page }) => {
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'GameMetrix Admin' })).toBeVisible()
  await expect(page.getByLabel('Username')).toBeVisible()
  await expect(page.getByLabel('Password')).toBeVisible()
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'noindex,nofollow,noarchive')
})

test('one-time account tokens leave the address bar after hydration', async ({ page }) => {
  const token = 'a'.repeat(48)
  await gotoHydrated(page, `/reset-password#token=${token}`)
  await expect(page).toHaveURL('http://127.0.0.1:4173/reset-password')
  await expect(page.locator('meta[name="referrer"]')).toHaveAttribute('content', 'no-referrer')

  await gotoHydrated(page, `/verify-email#token=${token}`)
  await expect(page).toHaveURL('http://127.0.0.1:4173/verify-email')
  await expect(page.getByLabel('Password')).toBeVisible()
  await expect(page.locator('meta[name="referrer"]')).toHaveAttribute('content', 'no-referrer')
})

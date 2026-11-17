import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

const MOCK_API = 'http://127.0.0.1:8001'

interface CatalogLogEntry {
  query: string
  q: string
  aborted: boolean
}

async function catalogLog(request: APIRequestContext): Promise<CatalogLogEntry[]> {
  return (await request.get(`${MOCK_API}/__test/catalog-log`)).json()
}

async function resetCatalogLog(request: APIRequestContext) {
  await request.delete(`${MOCK_API}/__test/catalog-log`)
}

async function gotoHydrated(page: Page, path: string) {
  const sessionLoaded = page.waitForResponse((response) => response.url().endsWith('/api/account/session'))
  await page.goto(path)
  await sessionLoaded
  await expect(page.locator('[data-game-slug="complete-test-game"]')).toBeVisible()
}

const searchBox = (page: Page) => page.getByLabel('Search games by title')

test('typing is debounced into one catalog request', async ({ page, request }) => {
  await gotoHydrated(page, '/')
  await page.waitForTimeout(300)
  await resetCatalogLog(request)

  await searchBox(page).pressSequentially('elden', { delay: 40 })
  // (The first page only: the next page is prefetched once it arrives.)
  await expect.poll(async () => (await catalogLog(request))
    .filter((entry) => entry.q && new URLSearchParams(entry.query).get('offset') === '0')
    .map((entry) => entry.q))
    .toEqual(['elden'])
})

test('a newer query cancels the older request and the old list stays, dimmed', async ({ page, request }) => {
  await gotoHydrated(page, '/')
  await page.waitForTimeout(300)
  await resetCatalogLog(request)

  await searchBox(page).fill('slow')
  await expect.poll(async () => (await catalogLog(request)).some((entry) => entry.q === 'slow')).toBe(true)
  // While the slow answer is pending the previous results remain on screen.
  await expect(page.locator('.game-list.is-refreshing [data-game-slug]').first()).toBeVisible()
  await expect(page.locator('.skeleton-card')).toHaveCount(0)

  await searchBox(page).pressSequentially('x')
  await expect.poll(async () => {
    const log = await catalogLog(request)
    return {
      firstAborted: log.find((entry) => entry.q === 'slow')?.aborted,
      second: log.some((entry) => entry.q === 'slowx'),
    }
  }).toEqual({ firstAborted: true, second: true })
})

test('an empty search says what was searched and offers to clear it', async ({ page }) => {
  await gotoHydrated(page, '/')
  await searchBox(page).fill('nothing here')
  await expect(page.getByText('No results for “nothing here”.')).toBeVisible()
  await page.getByRole('button', { name: 'Clear search' }).click()
  await expect(searchBox(page)).toHaveValue('')
  await expect(page.locator('[data-game-slug="complete-test-game"]')).toBeVisible()
})

test('filters in the URL are read by the loader and shown as chips', async ({ page, request }) => {
  await resetCatalogLog(request)
  const query = 'genre=RPG&year_min=2020&min_score=80&min_ratings=500&min_sources=2&critic=1&pt_max=20&sort=metrix_score&dir=asc'
  await page.goto(`/?${query}`)
  await expect(page.locator('[data-game-slug="complete-test-game"]')).toBeVisible()

  // The server-side render asked the API for exactly these filters.
  const ssr = (await catalogLog(request))[0]
  const params = new URLSearchParams(ssr.query)
  expect(Object.fromEntries(params)).toMatchObject({
    genre: 'RPG',
    year_min: '2020',
    min_score: '80',
    min_ratings: '500',
    min_live_sources: '2',
    require_critic: 'true',
    playtime_max_hours: '20',
    sort: 'metrix_score',
    direction: 'asc',
  })

  const chips = page.getByLabel('Active filters')
  for (const text of ['Genre: RPG', 'Year: 2020+', 'Score: 80+', 'Ratings: 500+', 'Sources: 2+ sources, critic score', 'Playtime: ≤ 20 h']) {
    await expect(chips.getByRole('button', { name: new RegExp(text.replace(/[+≤]/g, '\\$&')) })).toBeVisible()
  }
})

test('search and filter changes are written to the URL and survive a reload', async ({ page }) => {
  await gotoHydrated(page, '/?min_score=80')
  await searchBox(page).fill('zelda')
  await expect(page).toHaveURL(/q=zelda/)
  await expect(page).toHaveURL(/min_score=80/)

  await page.reload()
  await expect(searchBox(page)).toHaveValue('zelda')
  await expect(page.getByLabel('Active filters').getByRole('button', { name: /Score: 80\+/ })).toBeVisible()

  await page.getByLabel('Active filters').getByRole('button', { name: /Score: 80\+/ }).click()
  await expect(page).not.toHaveURL(/min_score/)
  await expect(page).toHaveURL(/q=zelda/)
})

test('browser back restores the previous filters from the URL', async ({ page }) => {
  await gotoHydrated(page, '/?genre=RPG')
  const chip = page.getByLabel('Active filters').getByRole('button', { name: /Genre: RPG/ })
  await expect(chip).toBeVisible()
  // The brand button returns to an unfiltered catalog as a new history entry.
  await page.locator('.brand').click()
  await expect(page).not.toHaveURL(/genre/)
  await expect(chip).toHaveCount(0)
  await page.goBack()
  await expect(page).toHaveURL(/genre=RPG/)
  await expect(chip).toBeVisible()
})

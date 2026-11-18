import { expect, test, type Page } from '@playwright/test'

async function gotoHydrated(page: Page, path: string) {
  const sessionLoaded = page.waitForResponse((response) => response.url().endsWith('/api/account/session'))
  await page.goto(path)
  await sessionLoaded
  await expect(page.locator('[data-game-slug="complete-test-game"]')).toBeVisible()
}

test('the home page shows the catalog size, not internal loading counters', async ({ page }) => {
  await gotoHydrated(page, '/')
  await expect(page.locator('.masthead-search-meta')).toContainText('48 games')
  const text = await page.locator('body').innerText()
  expect(text).not.toMatch(/providers ready/i)
  expect(text).not.toMatch(/\d+ \/ \d+ loaded/)
})

test('the Linux / Deck page says it is ProtonDB data, not Deck Verified', async ({ page }) => {
  await page.goto('/best/steam-deck-games')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Runs Well on Linux')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('ProtonDB')
  await expect(page.locator('.curated-heading')).toContainText('not Valve')
  await expect(page.locator('.curated-heading')).toContainText('Deck Verified')
})

test('ranking pages hide Admin, link years and genres, and search the catalog', async ({ page }) => {
  await page.goto('/best/linux-games')
  await expect(page.getByRole('link', { name: 'Admin' })).toHaveCount(0)
  const related = page.getByLabel('Related rankings')
  await expect(related.getByRole('link', { name: /^Best of \d{4}$/ }).first()).toBeVisible()
  await expect(related.getByRole('link', { name: 'RPG' })).toHaveAttribute('href', '/best/rpg-games')
  // The release year on a card goes to that year's ranking.
  await expect(page.locator('.curated-game-head p a').first()).toHaveAttribute('href', '/best/games/2024')

  await page.getByRole('search').getByLabel('Search games by title').fill('portal')
  await page.getByRole('search').getByRole('button', { name: 'Search' }).click()
  await expect(page).toHaveURL(/\/\?q=portal/)
})

test('the home footer links the year and genre rankings', async ({ page }) => {
  await gotoHydrated(page, '/')
  const footer = page.getByLabel('GameMetrix information')
  await expect(footer.getByRole('link', { name: /^Best of \d{4}$/ }).first()).toBeVisible()
  await expect(footer.getByRole('link', { name: 'RPG' })).toHaveAttribute('href', '/best/rpg-games')
})

test('cards have a labelled wishlist button and one Lists menu', async ({ page }) => {
  await gotoHydrated(page, '/')
  const card = page.locator('[data-game-slug="complete-test-game"]').first()
  await expect(card.getByRole('button', { name: /Wishlist/ })).toBeVisible()
  await expect(card.locator('[data-action="share"]')).toContainText('Share')
  await expect(card.locator('[data-action="completed"]')).toHaveCount(0)

  await card.getByRole('button', { name: /^Lists/ }).click()
  const completed = card.getByRole('menuitemcheckbox', { name: 'Completed' })
  await expect(completed).toBeVisible()
  await completed.click()
  await expect(completed).toHaveAttribute('aria-checked', 'true')
  await expect(card.getByRole('button', { name: /Lists \(1\)/ })).toBeVisible()
})

test('signed-out visitors are told lists live only in this browser', async ({ page }) => {
  await page.goto('/?view=watchlist')
  await expect(page.getByRole('note')).toContainText('saved only in this browser')
  await expect(page.getByRole('note').getByRole('link', { name: 'Log in' })).toHaveAttribute('href', '/login')

  await page.goto('/alerts')
  await expect(page.getByRole('note')).toContainText('only in this browser')
})

test('the game page leads with one score and keeps the rest in a disclosure', async ({ page }) => {
  await page.goto('/game/complete-test-game')
  const stats = page.locator('.dp-score-stats')
  await expect(stats).not.toContainText('Source avg')
  await expect(stats).not.toContainText('Rank score')
  const how = page.locator('.dp-score-how')
  await expect(how).not.toHaveAttribute('open', '')
  await how.locator('summary').click()
  await expect(how).toContainText('Source average')
  await expect(how).toContainText('weighted average')
})

test('About explains the weighted formula with a worked example', async ({ page }) => {
  await page.goto('/about')
  const about = page.locator('.about-rating')
  await expect(about).toContainText('weighted average')
  await expect(about).toContainText('Metacritic 32%')
  await expect(about).toContainText('reliability')
  await expect(about).toContainText('93.5')
  await expect(about).toContainText('81.9')
  await expect(about).not.toContainText('÷ 4')
})

test('the filter panel offers year and playtime as free number fields', async ({ page }) => {
  await gotoHydrated(page, '/')
  await page.getByRole('button', { name: /Filters/i }).first().click()
  await expect(page.getByLabel('Year from')).toBeVisible()
  await expect(page.getByLabel('Year to')).toBeVisible()
  await page.getByRole('button', { name: /More Options/ }).click()
  await page.getByLabel('Maximum playtime in hours').fill('20')
  await expect(page.getByLabel('Active filters').getByRole('button', { name: /Playtime: ≤ 20 h/ })).toBeVisible()
})

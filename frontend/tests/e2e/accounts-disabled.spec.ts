import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

// Production runs with ACCOUNT_AUTH_ENABLED=false until e-mail delivery works. The
// session endpoint then answers 200 with accounts_enabled=false (the mock switches
// to that mode on the gm_test_accounts=off cookie) and no login entry point shows.
test.beforeEach(async ({ context }) => {
  await context.addCookies([{ name: 'gm_test_accounts', value: 'off', url: 'http://127.0.0.1:4173' }])
})

async function gotoHydrated(page: Page, path: string) {
  const session = page.waitForResponse((response) => response.url().endsWith('/api/account/session'))
  await page.goto(path)
  const response = await session
  expect(response.status()).toBe(200)
  expect(await response.json()).toMatchObject({ account: null, accounts_enabled: false })
}

test('accounts switched off: no console error and no Login entry points', async ({ page }) => {
  const consoleErrors: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })

  await gotoHydrated(page, '/')
  await expect(page.getByRole('heading', { name: 'Game scores and PC compatibility rankings' })).toBeVisible()
  await expect(page.getByTitle('Settings')).toBeVisible()
  await expect(page.getByTitle('Login')).toHaveCount(0)

  await gotoHydrated(page, '/deals')
  await expect(page.locator('.curated-topbar')).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Account navigation' })).toHaveCount(0)

  await page.setViewportSize({ width: 390, height: 844 })
  await gotoHydrated(page, '/')
  await page.getByRole('button', { name: 'More' }).click()
  const menu = page.locator('.mobile-more-menu')
  await expect(menu.getByText('Settings')).toBeVisible()
  await expect(menu.getByText('Login')).toHaveCount(0)

  expect(consoleErrors.filter((text) => /account|503/i.test(text))).toEqual([])
})

test('accounts switched off: /login explains calmly instead of showing a form', async ({ page }) => {
  await gotoHydrated(page, '/login')
  await expect(page.getByRole('heading', { name: 'Accounts unavailable' })).toBeVisible()
  await expect(page.getByRole('status')).toContainText('Accounts are switched off for now')
  await expect(page.getByLabel('Password')).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Back to the catalog' })).toHaveAttribute('href', '/')
})

test('accounts switched off: guest list notice drops the login prompt', async ({ page }) => {
  await gotoHydrated(page, '/alerts')
  const note = page.getByRole('note')
  await expect(note).toContainText('only in this browser')
  await expect(note.getByRole('link', { name: 'Log in' })).toHaveCount(0)
})

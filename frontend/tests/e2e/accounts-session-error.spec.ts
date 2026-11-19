import { expect, test } from '@playwright/test'
import type { BrowserContext, Page } from '@playwright/test'

// A failed session read (network error, 503 load shedding) is not the same as
// accounts being switched off: the auth pages offer a retry instead of the
// "switched off" note, and login entry points stay hidden as while unknown.
// The mock fails /api/account/session on the gm_test_session=fail cookie.
const ORIGIN = 'http://127.0.0.1:4173'

async function failSession(context: BrowserContext) {
  await context.addCookies([{ name: 'gm_test_session', value: 'fail', url: ORIGIN }])
}

async function gotoWithFailedSession(page: Page, path: string) {
  const session = page.waitForResponse((response) => response.url().endsWith('/api/account/session'))
  await page.goto(path)
  expect((await session).status()).toBe(503)
}

test('session read fails: /login offers a retry, not the switched-off note', async ({ page, context }) => {
  await failSession(context)
  await gotoWithFailedSession(page, '/login')

  const alert = page.getByRole('alert')
  await expect(alert).toContainText('Accounts could not be reached')
  await expect(page.getByText('Accounts are switched off')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Accounts unavailable' })).toHaveCount(0)
  await expect(page.getByRole('textbox', { name: 'Password' })).toHaveCount(0)

  await context.clearCookies({ name: 'gm_test_session' })
  await alert.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByRole('textbox', { name: 'Password' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Log in' })).toBeVisible()
})

test('session read fails: /reset-password keeps its token through the retry', async ({ page, context }) => {
  await failSession(context)
  await gotoWithFailedSession(page, '/reset-password?token=reset-token-123')
  await expect(page.getByRole('alert')).toContainText('Accounts could not be reached')
  await expect(page).toHaveURL(/\/reset-password$/)

  await context.clearCookies({ name: 'gm_test_session' })
  const resetRequest = page.waitForRequest((request) => request.url().endsWith('/api/account/password/reset'))
  await page.getByRole('button', { name: 'Try again' }).click()
  await page.getByRole('textbox', { name: 'Password' }).fill('a-new-long-password-1')
  await page.getByRole('button', { name: 'Choose a new password' }).click()
  expect((await resetRequest).postDataJSON()).toMatchObject({ token: 'reset-token-123' })
})

test('session read fails: no Login entry points, like while unknown', async ({ page, context }) => {
  await failSession(context)
  await gotoWithFailedSession(page, '/')
  await expect(page.getByRole('heading', { name: 'Game scores and PC compatibility rankings' })).toBeVisible()
  await expect(page.getByTitle('Settings')).toBeVisible()
  await expect(page.getByTitle('Login')).toHaveCount(0)

  await gotoWithFailedSession(page, '/alerts')
  const note = page.getByRole('note')
  await expect(note).toContainText('only in this browser')
  await expect(note.getByRole('link', { name: 'Log in' })).toHaveCount(0)
})

test('while the session read is pending no Login entry point flashes', async ({ page }) => {
  let release: () => void = () => undefined
  const held = new Promise<void>((resolveHold) => { release = resolveHold })
  await page.route('**/api/account/session', async (route) => {
    await held
    await route.continue()
  })
  await page.goto('/')
  await expect(page.getByTitle('Settings')).toBeVisible()
  await expect(page.getByTitle('Login')).toHaveCount(0)
  release()
  // The default mock has accounts on, so the entry point appears once known.
  await expect(page.getByTitle('Login')).toBeVisible()
})

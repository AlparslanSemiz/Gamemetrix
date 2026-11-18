import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { expect, test, type Page } from '@playwright/test'
import { addBeaconNonce } from '../../src/csp.server'

// The SSR app sends the CSP (nginx sends none for gamemetrix.me). Inline scripts must run via the
// per-response nonce, never 'unsafe-inline'. Chromium reports violations as console errors and as
// securitypolicyviolation events; both are collected.
const PAGES = ['/', '/game/complete-test-game', '/best/linux-games', '/about'] as const

async function watchViolations(page: Page): Promise<string[]> {
  const violations: string[] = []
  page.on('console', (message) => {
    if (/content security policy|refused to (execute|load|apply)/i.test(message.text())) violations.push(message.text())
  })
  await page.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', (event) => {
      console.error(`CSP violation: ${event.violatedDirective} ${event.blockedURI}`)
    })
  })
  return violations
}

async function stubThirdParties(page: Page): Promise<{ requested: string[] }> {
  const requested: string[] = []
  await page.route(/^https:\/\/(static\.cloudflareinsights\.com|www\.googletagmanager\.com|www\.google-analytics\.com)\//, async (route) => {
    requested.push(route.request().url())
    await route.fulfill({ status: 200, contentType: 'application/javascript', body: '' })
  })
  return { requested }
}

test.describe('Content-Security-Policy', () => {
  test('HTML carries one nonce-based CSP without unsafe-inline in script-src', async ({ request }) => {
    for (const path of PAGES) {
      const response = await request.get(path)
      const header = response.headers()['content-security-policy']
      expect(header, path).toBeTruthy()
      const scriptSrc = header.split(';').map((part) => part.trim()).find((part) => part.startsWith('script-src ')) ?? ''
      expect(scriptSrc, path).not.toContain('unsafe-inline')
      expect(scriptSrc, path).toContain("'strict-dynamic'")
      const nonce = /'nonce-([^']+)'/.exec(scriptSrc)?.[1]
      expect(nonce, path).toBeTruthy()
      expect(header).toContain("frame-ancestors 'none'")
      expect(header).toContain('https://www.youtube-nocookie.com')

      // Every executable inline script and the beacon carry that nonce.
      const html = await response.text()
      const tags = [...html.matchAll(/<script\b([^>]*)>/g)].map((match) => match[1])
      const executable = tags.filter((attrs) => !/type="application\/ld\+json"/.test(attrs))
      expect(executable.length, path).toBeGreaterThan(0)
      for (const attrs of executable) expect(attrs, `${path} <script${attrs}>`).toContain(`nonce="${nonce}"`)
    }
  })

  test('the Cloudflare beacon tag from root.tsx gets the nonce, other scripts are untouched', () => {
    const beacon = renderToStaticMarkup(createElement('script', {
      defer: true,
      src: 'https://static.cloudflareinsights.com/beacon.min.js',
      'data-cf-beacon': JSON.stringify({ token: 't' }),
    }))
    const other = '<script src="/assets/entry.js"></script>'
    const html = addBeaconNonce(`${beacon}${other}`, 'abc123')
    expect(html).toContain('<script nonce="abc123" defer=""')
    expect(html).toContain(other)
  })

  test('each response gets a fresh nonce', async ({ request }) => {
    const nonces = new Set<string>()
    for (let i = 0; i < 3; i += 1) {
      const header = (await request.get('/about')).headers()['content-security-policy']
      nonces.add(/'nonce-([^']+)'/.exec(header)?.[1] ?? '')
    }
    expect(nonces.size).toBe(3)
  })

  for (const path of PAGES) {
    test(`${path} hydrates with no CSP violations`, async ({ page }) => {
      const violations = await watchViolations(page)
      await stubThirdParties(page)
      await page.goto(path)
      await page.waitForLoadState('networkidle')
      // Hydration proof: the consent banner is client-rendered state; accepting it must remove it.
      await page.getByRole('button', { name: /accept|allow|agree/i }).first().click()
      await expect(page.locator('.analytics-consent')).toHaveCount(0)
      expect(violations).toEqual([])
    })
  }

  test('accepting analytics lets the GA/GTM loader run', async ({ page }) => {
    const violations = await watchViolations(page)
    const { requested } = await stubThirdParties(page)
    await page.goto('/about')
    await page.locator('.analytics-consent-primary').click()
    await expect.poll(() => requested.some((url) => url.includes('googletagmanager.com/gtag/js?id=G-E2ETEST123'))).toBe(true)
    expect(violations).toEqual([])
  })
})

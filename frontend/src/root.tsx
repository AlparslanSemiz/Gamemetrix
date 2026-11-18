import { Links, Meta, Outlet, Scripts, ScrollRestoration } from 'react-router'
import type { ReactNode } from 'react'
import { AnalyticsConsentBanner } from './components/AnalyticsConsentBanner'
import { RouteErrorPage } from './components/RouteErrorPage'
import { PageViewTracker } from './components/PageViewTracker'
import { SiteLegalFooter } from './components/SiteLegalFooter'
import { AccountProvider } from './state/AccountProvider'
import { CollectionsProvider } from './state/CollectionsProvider'
import './index.css'

const CLOUDFLARE_BEACON_URL = 'https://static.cloudflareinsights.com/beacon.min.js'
// Set only for production images (images.yml); local, test and Lighthouse builds load no beacon.
const CLOUDFLARE_BEACON_TOKEN = String(import.meta.env.VITE_CF_BEACON_TOKEN ?? '').trim()

export function Layout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="theme-color" content="#0f1014" />
        <link rel="icon" href="/favicon.svg" />
        <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
        <Meta />
        <Links />
        {/* Cloudflare Web Analytics: cookieless page-view counts, no consent needed. */}
        {CLOUDFLARE_BEACON_TOKEN && (
          <script
            defer
            src={CLOUDFLARE_BEACON_URL}
            data-cf-beacon={JSON.stringify({ token: CLOUDFLARE_BEACON_TOKEN })}
          />
        )}
      </head>
      <body>
        <a className="skip-link" href="#main-content">Skip to main content</a>
        {children}
        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  )
}

export default function Root() {
  return (
    <CollectionsProvider>
      <AccountProvider>
        <PageViewTracker />
        <Outlet />
        <SiteLegalFooter />
        <AnalyticsConsentBanner />
      </AccountProvider>
    </CollectionsProvider>
  )
}

export function ErrorBoundary() {
  return <RouteErrorPage />
}

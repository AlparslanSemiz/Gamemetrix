import {
  isRouteErrorResponse,
  Links,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
  useRouteError,
} from 'react-router'
import type { ReactNode } from 'react'
import { AnalyticsConsentBanner } from './components/AnalyticsConsentBanner'
import { PageViewTracker } from './components/PageViewTracker'
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
        <AnalyticsConsentBanner />
      </AccountProvider>
    </CollectionsProvider>
  )
}

export function ErrorBoundary() {
  const error = useRouteError()
  const status = isRouteErrorResponse(error) ? error.status : 500
  const title = status === 404
    ? 'Page not found'
    : status === 429 || status === 503
      ? 'Busy right now, please try again in a moment'
      : 'Something went wrong'
  return (
    <main className="route-error">
      <a className="route-error-brand" href="/">GameMetrix</a>
      <p>{status}</p>
      <h1>{title}</h1>
      <a href="/">Return to the catalog</a>
    </main>
  )
}

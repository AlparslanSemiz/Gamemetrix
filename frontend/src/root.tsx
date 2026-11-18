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

// Automated browsers (navigator.webdriver: tests, audits, CI) are counted in a separate "testler"
// site (CLOUDFLARE_TEST_BEACON_TOKEN), so real visits stay clean and test traffic is still measured.
// Not loaded for the owner's own browsers (localStorage notrack=1; ?notrack=1 sets it, ?notrack=0 clears it).
// localStorage can throw (private mode); then the beacon loads as usual. Inline script: the CSP
// already allows 'unsafe-inline'. "<" is escaped so the token cannot close the script element.
const CLOUDFLARE_TEST_BEACON_TOKEN = '0ead9632eeb34bfdbca243e769478158'

const CLOUDFLARE_BEACON_LOADER = CLOUDFLARE_BEACON_TOKEN
  ? `(function(){try{var n=new URLSearchParams(location.search).get('notrack');if(n==='1')localStorage.setItem('notrack','1');else if(n==='0')localStorage.removeItem('notrack')}catch(e){}try{if(localStorage.getItem('notrack')==='1')return}catch(e){}var s=document.createElement('script');s.defer=true;s.src=${JSON.stringify(CLOUDFLARE_BEACON_URL)};s.setAttribute('data-cf-beacon',navigator.webdriver?${JSON.stringify(JSON.stringify({ token: CLOUDFLARE_TEST_BEACON_TOKEN }))}:${JSON.stringify(JSON.stringify({ token: CLOUDFLARE_BEACON_TOKEN })).replace(/</g, '\\u003c')});document.head.appendChild(s)})();`
  : ''

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
        {CLOUDFLARE_BEACON_LOADER && <script dangerouslySetInnerHTML={{ __html: CLOUDFLARE_BEACON_LOADER }} />}
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

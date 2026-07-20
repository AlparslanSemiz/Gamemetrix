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
import { PageViewTracker } from './components/PageViewTracker'
import { AccountProvider } from './state/AccountProvider'
import { CollectionsProvider } from './state/CollectionsProvider'
import './index.css'

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
      </AccountProvider>
    </CollectionsProvider>
  )
}

export function ErrorBoundary() {
  const error = useRouteError()
  const status = isRouteErrorResponse(error) ? error.status : 500
  const title = status === 404 ? 'Page not found' : 'Something went wrong'
  return (
    <main className="route-error">
      <a className="route-error-brand" href="/">GameMetrix</a>
      <p>{status}</p>
      <h1>{title}</h1>
      <a href="/">Return to the catalog</a>
    </main>
  )
}

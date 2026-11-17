import { isRouteErrorResponse, useRouteError } from 'react-router'

/** Shared error screen for route ErrorBoundaries; 429/503 offer a retry. */
export function RouteErrorPage() {
  const error = useRouteError()
  const status = isRouteErrorResponse(error) ? error.status : 500
  const busy = status === 429 || status === 503
  const title = status === 404
    ? 'Page not found'
    : busy
      ? 'Busy right now, please try again in a moment'
      : 'Something went wrong'
  return (
    <main id="main-content" className="route-error">
      <a className="route-error-brand" href="/">GameMetrix</a>
      <p>{status}</p>
      <h1>{title}</h1>
      {busy ? (
        <button type="button" className="apply-button" onClick={() => window.location.reload()}>
          Try again
        </button>
      ) : null}
      <a href="/">Return to the catalog</a>
    </main>
  )
}

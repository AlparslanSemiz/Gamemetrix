import { useEffect, useState } from 'react'
import type { MetaFunction } from 'react-router'
import { Link } from 'react-router'
import { AccountApiError, unsubscribeEmailDigest } from '../services/account'
import '../components/AccountAuth.css'

export const meta: MetaFunction = () => [
  { title: 'Email Preferences | GameMetrix' },
  { name: 'robots', content: 'noindex,nofollow' },
  { name: 'referrer', content: 'no-referrer' },
]

export const headers = () => ({ 'Cache-Control': 'private, no-store' })

export default function UnsubscribeRoute() {
  const [token] = useState(() => {
    if (typeof window === 'undefined') return ''
    return new URLSearchParams(window.location.hash.slice(1)).get('token') ?? ''
  })
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    if (token) window.history.replaceState(window.history.state, '', '/unsubscribe')
  }, [token])

  const unsubscribe = async () => {
    setError(null)
    setIsSubmitting(true)
    try {
      if (!token) throw new Error('The unsubscribe token is missing.')
      const result = await unsubscribeEmailDigest(token)
      setMessage(result.message)
    } catch (caught) {
      setError(
        caught instanceof AccountApiError || caught instanceof Error
          ? caught.message
          : 'The request could not be completed.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="account-auth-shell">
      <section className="account-auth-dialog" aria-labelledby="unsubscribe-title">
        <h1 id="unsubscribe-title">Email preferences</h1>
        <p>Confirm that you want to stop GameMetrix watchlist update emails.</p>
        {error ? <p className="account-auth-status is-error" role="alert">{error}</p> : null}
        {message ? <p className="account-auth-status is-success" role="status">{message}</p> : null}
        {!message ? (
          <button
            type="button"
            className="account-auth-submit"
            disabled={isSubmitting || !token}
            onClick={unsubscribe}
          >
            {isSubmitting ? 'Working...' : 'Unsubscribe'}
          </button>
        ) : null}
        <div className="account-auth-links"><Link to="/settings">Manage account settings</Link></div>
      </section>
    </main>
  )
}

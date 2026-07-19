import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { trackPageView } from '../services/analytics'

const VISITOR_ID_KEY = 'gamemetrix.visitorId.v1'
const SESSION_ID_KEY = 'gamemetrix.sessionId.v1'

function createVisitorId(): string {
  if (crypto.randomUUID) return crypto.randomUUID()
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
}

function getVisitorId(): string {
  const existing = window.localStorage.getItem(VISITOR_ID_KEY)
  if (existing) return existing
  const next = createVisitorId()
  window.localStorage.setItem(VISITOR_ID_KEY, next)
  return next
}

function getSessionId(): string {
  const existing = window.sessionStorage.getItem(SESSION_ID_KEY)
  if (existing) return existing
  const next = createVisitorId()
  window.sessionStorage.setItem(SESSION_ID_KEY, next)
  return next
}

export function PageViewTracker() {
  const location = useLocation()

  useEffect(() => {
    if (location.pathname.startsWith('/admin')) return

    const timer = window.setTimeout(() => {
      trackPageView({
        path: `${location.pathname}${location.search}`,
        visitor_id: getVisitorId(),
        session_id: getSessionId(),
        referrer: document.referrer || undefined,
        title: document.title,
        screen_width: window.innerWidth,
        screen_height: window.innerHeight,
        language: navigator.language || undefined,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || undefined,
      })
    }, 150)

    return () => window.clearTimeout(timer)
  }, [location.pathname, location.search])

  return null
}

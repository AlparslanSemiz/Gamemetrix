import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { getAnalyticsSessionId, getAnalyticsVisitorId, trackPageView } from '../services/analytics'

export function PageViewTracker() {
  const location = useLocation()
  const referrerRecorded = useRef(false)

  useEffect(() => {
    if (location.pathname.startsWith('/admin')) return

    const timer = window.setTimeout(() => {
      const referrer = referrerRecorded.current ? undefined : document.referrer || undefined
      referrerRecorded.current = true
      trackPageView({
        path: `${location.pathname}${location.search}`,
        visitor_id: getAnalyticsVisitorId(),
        session_id: getAnalyticsSessionId(),
        referrer,
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

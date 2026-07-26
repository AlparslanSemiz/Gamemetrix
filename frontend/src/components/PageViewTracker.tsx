import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router'
import { getAnalyticsSessionId, getAnalyticsVisitorId, trackPageView } from '../services/analytics'
import { useAnalyticsPreferences } from '../services/analyticsConsent'
import { trackGooglePageView } from '../services/googleAnalytics'

export function PageViewTracker() {
  const location = useLocation()
  const referrerRecorded = useRef(false)
  const { consent, internal } = useAnalyticsPreferences()

  useEffect(() => {
    if (
      location.pathname.startsWith('/admin')
      || consent !== 'granted'
      || internal
      || navigator.doNotTrack === '1'
    ) return

    const timer = window.setTimeout(() => {
      const path = `${location.pathname}${location.search}`
      const referrer = referrerRecorded.current ? undefined : document.referrer || undefined
      referrerRecorded.current = true
      trackPageView({
        path,
        visitor_id: getAnalyticsVisitorId(),
        session_id: getAnalyticsSessionId(),
        referrer,
        title: document.title,
        screen_width: window.innerWidth,
        screen_height: window.innerHeight,
        language: navigator.language || undefined,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || undefined,
      })
      trackGooglePageView(path, document.title)
    }, 150)

    return () => window.clearTimeout(timer)
  }, [consent, internal, location.pathname, location.search])

  return null
}

import { ShieldCheck } from 'lucide-react'

import {
  setAnalyticsConsent,
  useAnalyticsPreferences,
} from '../services/analyticsConsent'
import './AnalyticsConsentBanner.css'

export function AnalyticsConsentBanner() {
  const { consent } = useAnalyticsPreferences()
  if (consent !== 'unset') return null

  return (
    <aside className="analytics-consent" aria-label="Analytics privacy choice">
      <ShieldCheck size={22} aria-hidden="true" />
      <div>
        <strong>Privacy-conscious analytics</strong>
        <p>
          If you allow it, we measure page views and clicks with an anonymous
          visitor ID stored in your browser (our own analytics, plus Google
          Analytics where enabled). Advertising personalization stays off and
          nothing is collected before you choose. Change it any time in Settings.{' '}
          <a href="/privacy">Privacy policy</a>
        </p>
      </div>
      <div className="analytics-consent-actions">
        <button type="button" className="analytics-consent-secondary" onClick={() => setAnalyticsConsent('denied')}>
          Decline
        </button>
        <button type="button" className="analytics-consent-primary" onClick={() => setAnalyticsConsent('granted')}>
          Allow analytics
        </button>
      </div>
    </aside>
  )
}

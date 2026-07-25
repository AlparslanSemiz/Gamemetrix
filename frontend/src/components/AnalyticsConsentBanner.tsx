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
          Allow pseudonymous browser and session measurement so we can improve
          GameMetrix. Google Analytics may be used when configured; advertising
          personalization stays disabled. You can change this in Settings.
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

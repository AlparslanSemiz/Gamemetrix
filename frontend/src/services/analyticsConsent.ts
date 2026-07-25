import { useSyncExternalStore } from 'react'

export type AnalyticsConsent = 'granted' | 'denied' | 'unset'

const CONSENT_KEY = 'gamemetrix.analyticsConsent.v1'
const INTERNAL_TRAFFIC_KEY = 'gamemetrix.analyticsInternal.v1'
const PREFERENCE_EVENT = 'gamemetrix:analytics-preference'

function readStorage(key: string): string | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeStorage(key: string, value: string): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // The in-memory behavior remains privacy-safe when storage is unavailable.
  }
  window.dispatchEvent(new Event(PREFERENCE_EVENT))
}

export function getAnalyticsConsent(): AnalyticsConsent {
  const value = readStorage(CONSENT_KEY)
  return value === 'granted' || value === 'denied' ? value : 'unset'
}

export function setAnalyticsConsent(consent: Exclude<AnalyticsConsent, 'unset'>): void {
  writeStorage(CONSENT_KEY, consent)
  window.gtag?.('consent', 'update', {
    analytics_storage: consent,
    ad_storage: 'denied',
    ad_user_data: 'denied',
    ad_personalization: 'denied',
  })
}

export function isInternalAnalyticsTraffic(): boolean {
  return readStorage(INTERNAL_TRAFFIC_KEY) === 'true'
}

export function setInternalAnalyticsTraffic(internal: boolean): void {
  writeStorage(INTERNAL_TRAFFIC_KEY, String(internal))
}

export function analyticsCollectionAllowed(): boolean {
  return getAnalyticsConsent() === 'granted' && !isInternalAnalyticsTraffic()
}

function subscribe(onStoreChange: () => void): () => void {
  if (typeof window === 'undefined') return () => undefined
  window.addEventListener(PREFERENCE_EVENT, onStoreChange)
  window.addEventListener('storage', onStoreChange)
  return () => {
    window.removeEventListener(PREFERENCE_EVENT, onStoreChange)
    window.removeEventListener('storage', onStoreChange)
  }
}

export function useAnalyticsPreferences() {
  const consent = useSyncExternalStore(
    subscribe,
    getAnalyticsConsent,
    () => 'unset' as const,
  )
  const internal = useSyncExternalStore(
    subscribe,
    isInternalAnalyticsTraffic,
    () => false,
  )
  return { consent, internal }
}

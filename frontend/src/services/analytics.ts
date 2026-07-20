const VISITOR_ID_KEY = 'gamemetrix.visitorId.v1'
const SESSION_ID_KEY = 'gamemetrix.sessionId.v1'
let memoryVisitorId: string | null = null
let memorySessionId: string | null = null

function createAnalyticsId(): string {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
}

function storedAnalyticsId(storage: Storage, key: string): string {
  const existing = storage.getItem(key)
  if (existing && existing.length <= 128 && /^[a-zA-Z0-9._-]+$/.test(existing)) return existing
  const next = createAnalyticsId()
  storage.setItem(key, next)
  return next
}

export function getAnalyticsVisitorId(): string {
  try {
    return storedAnalyticsId(window.localStorage, VISITOR_ID_KEY)
  } catch {
    memoryVisitorId ??= createAnalyticsId()
    return memoryVisitorId
  }
}

export function getAnalyticsSessionId(): string {
  try {
    return storedAnalyticsId(window.sessionStorage, SESSION_ID_KEY)
  } catch {
    memorySessionId ??= createAnalyticsId()
    return memorySessionId
  }
}

export interface PageViewEvent {
  path: string
  visitor_id: string
  referrer?: string
  title?: string
  screen_width?: number
  screen_height?: number
  session_id?: string
  language?: string
  timezone?: string
}

export type ProductEventType =
  | 'signup_completed'
  | 'login_completed'
  | 'wishlist_add'
  | 'alert_enabled'
  | 'store_outbound'
  | 'share'

export function trackPageView(event: PageViewEvent): void {
  if (navigator.doNotTrack === '1') return

  const body = JSON.stringify(event)
  const url = '/api/analytics/page-view'

  if ('sendBeacon' in navigator) {
    const blob = new Blob([body], { type: 'application/json' })
    if (navigator.sendBeacon(url, blob)) return
  }

  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    credentials: 'include',
    keepalive: true,
  }).catch(() => {})
}

export function trackProductEvent(
  eventType: ProductEventType,
  properties: Record<string, string | number | boolean | null> = {},
): void {
  if (navigator.doNotTrack === '1') return
  fetch('/api/analytics/event', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      event_type: eventType,
      visitor_id: getAnalyticsVisitorId(),
      path: `${window.location.pathname}${window.location.search}`,
      properties,
    }),
    keepalive: true,
  }).catch(() => {})
}

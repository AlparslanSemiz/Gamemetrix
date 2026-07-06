import { API_BASE_URL } from './api'

export interface PageViewEvent {
  path: string
  visitor_id: string
  referrer?: string
  title?: string
  screen_width?: number
  screen_height?: number
}

export function trackPageView(event: PageViewEvent): void {
  if (navigator.doNotTrack === '1') return

  const body = JSON.stringify(event)
  const url = `${API_BASE_URL}/api/analytics/page-view`

  if ('sendBeacon' in navigator) {
    const blob = new Blob([body], { type: 'application/json' })
    if (navigator.sendBeacon(url, blob)) return
  }

  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    keepalive: true,
  }).catch(() => {})
}

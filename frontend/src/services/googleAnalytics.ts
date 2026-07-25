const measurementId = String(import.meta.env.VITE_GA_MEASUREMENT_ID ?? '').trim()

declare global {
  interface Window {
    dataLayer?: unknown[]
    gtag?: (...args: unknown[]) => void
  }
}

let initialized = false

export function googleAnalyticsConfigured(): boolean {
  return /^G-[A-Z0-9]+$/i.test(measurementId)
}

export function initializeGoogleAnalytics(): void {
  if (initialized || !googleAnalyticsConfigured() || typeof document === 'undefined') return
  initialized = true

  window.dataLayer = window.dataLayer ?? []
  window.gtag = (...args: unknown[]) => {
    window.dataLayer?.push(args)
  }
  window.gtag('consent', 'default', {
    analytics_storage: 'granted',
    ad_storage: 'denied',
    ad_user_data: 'denied',
    ad_personalization: 'denied',
  })
  window.gtag('js', new Date())
  window.gtag('config', measurementId, {
    send_page_view: false,
    allow_google_signals: false,
    allow_ad_personalization_signals: false,
  })

  const script = document.createElement('script')
  script.async = true
  script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(measurementId)}`
  document.head.append(script)
}

export function trackGooglePageView(path: string, title: string): void {
  initializeGoogleAnalytics()
  window.gtag?.('event', 'page_view', {
    page_location: `${window.location.origin}${path}`,
    page_path: path,
    page_title: title,
  })
}

export function trackGoogleEvent(
  eventName: string,
  properties: Record<string, string | number | boolean | null>,
): void {
  initializeGoogleAnalytics()
  window.gtag?.('event', eventName, properties)
}

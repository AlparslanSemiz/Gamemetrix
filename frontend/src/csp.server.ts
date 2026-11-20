import { randomBytes } from 'node:crypto'

/** A fresh, unguessable value for one SSR response (128 bits, base64). */
export function generateNonce(): string {
  return randomBytes(16).toString('base64')
}

/**
 * Content-Security-Policy for SSR HTML on gamemetrix.me. nginx sends no CSP for that host
 * (see nginx.conf, `map $host $gm_csp`); the other directives mirror the policy it used to send.
 *
 * script-src: the nonce authorises our inline scripts (hydration data, Cloudflare beacon);
 * 'strict-dynamic' lets those trusted scripts load further ones (the GA/GTM loader), which makes
 * modern browsers ignore 'self'/https: — those two are only the fallback for browsers without
 * strict-dynamic support. No 'unsafe-inline'.
 */
export function buildContentSecurityPolicy(nonce: string): string {
  return [
    "default-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-ancestors 'none'",
    "form-action 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic' https:`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: https:",
    "font-src 'self' data:",
    "connect-src 'self' https://api.gamemetrix.me https://www.google-analytics.com https://*.google-analytics.com https://cloudflareinsights.com",
    'frame-src https://www.youtube.com https://www.youtube-nocookie.com',
    "media-src 'self' https:",
    'upgrade-insecure-requests',
  ].join('; ')
}

// The beacon tag itself, or root.tsx's inline loader that inserts it (marked data-cf-loader).
const BEACON_SCRIPT_TAG = /<script (?=[^>]*\b(?:src="https:\/\/static\.cloudflareinsights\.com\/|data-cf-loader=))/g

/**
 * Gives the Cloudflare beacon tag from root.tsx its nonce. React's own components pick the nonce
 * up from <ServerRouter nonce>, but Layout has no access to it, so the tag is completed here
 * while the document head streams out.
 */
export function addBeaconNonce(html: string, nonce: string): string {
  return html.replace(BEACON_SCRIPT_TAG, `<script nonce="${nonce}" `)
}

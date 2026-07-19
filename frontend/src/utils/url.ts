const FALLBACK_BASE_URL = 'https://gamemetrix.invalid'
const SAFE_LINK_PROTOCOLS = new Set(['http:', 'https:'])

export function safeExternalUrl(value: string | null | undefined): string | null {
  const trimmed = value?.trim()
  if (!trimmed) return null

  try {
    const base = typeof window !== 'undefined' ? window.location.origin : FALLBACK_BASE_URL
    const url = new URL(trimmed, base)
    return SAFE_LINK_PROTOCOLS.has(url.protocol) ? url.href : null
  } catch {
    return null
  }
}

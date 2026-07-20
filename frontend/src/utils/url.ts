const SAFE_LINK_PROTOCOLS = new Set(['http:', 'https:'])

export function safeExternalUrl(value: string | null | undefined): string | null {
  const trimmed = value?.trim()
  if (!trimmed) return null

  try {
    const url = new URL(trimmed)
    if (!SAFE_LINK_PROTOCOLS.has(url.protocol) || url.username || url.password) return null
    return url.href
  } catch {
    return null
  }
}

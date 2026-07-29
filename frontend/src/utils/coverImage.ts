import type { CatalogGame, Game } from '../types/game'

const XML_ESCAPES: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;' }

// Generated SVG placeholder used whenever a game has no usable art. Shared so
// cards, the series strip, and the detail gallery all fall back identically.
export function fallbackCoverUrl(title: string): string {
  const words = title.split(/\s+/).filter(Boolean).slice(0, 4).join(' ')
  const safeTitle = (words || 'GameMetrix').replace(/[&<>]/g, (c) => XML_ESCAPES[c])
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900">
      <defs>
        <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stop-color="#20242c"/>
          <stop offset="0.55" stop-color="#15171d"/>
          <stop offset="1" stop-color="#22352a"/>
        </linearGradient>
      </defs>
      <rect width="1600" height="900" fill="url(#bg)"/>
      <rect x="64" y="64" width="1472" height="772" rx="28" fill="none" stroke="#3c4642" stroke-width="6"/>
      <text x="120" y="450" fill="#f1f3f7" font-family="Inter, Segoe UI, sans-serif" font-size="86" font-weight="800">${safeTitle}</text>
      <text x="120" y="540" fill="#a78bfa" font-family="Inter, Segoe UI, sans-serif" font-size="34" font-weight="800">GAMEMETRIX</text>
    </svg>`
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`
}

// Storefront art that carries no real cover: empty, a literal none/null, or a
// known generic placeholder path. Steam serves its grey logo capsule for apps
// that never uploaded key art — prefer a screenshot over these.
const PLACEHOLDER_URL_MARKERS = ['steam_default', 'default_app', 'no_image', 'placeholder', 'blank.gif']

export function isPlaceholderImageUrl(url: string | null | undefined): boolean {
  if (!url) return true
  const value = url.trim().toLowerCase()
  if (value === '' || value === 'none' || value === 'null' || value === 'undefined') return true
  return PLACEHOLDER_URL_MARKERS.some((marker) => value.includes(marker))
}

// A cover that decodes to a small, near-square image is a logo/placeholder, not
// a 16:9 key-art frame. This catches Steam's grey logo capsule at runtime when
// its URL looks ordinary, so we can demote it to a real screenshot.
export function looksLikePlaceholderImage(naturalWidth: number, naturalHeight: number): boolean {
  if (naturalWidth === 0 || naturalHeight === 0) return false
  const ratio = naturalWidth / naturalHeight
  return ratio > 0.8 && ratio < 1.25 && naturalWidth < 600
}

// Best real image for a card/detail cover: a valid cover, else a screenshot,
// else image_url, else the generated fallback. Never returns a placeholder URL.
export function bestCoverUrl(
  game: Pick<CatalogGame, 'title' | 'cover_url' | 'image_url'> & {
    screenshots?: string[]
  },
): string {
  if (!isPlaceholderImageUrl(game.cover_url)) return game.cover_url
  const screenshot = (game.screenshots ?? []).find((s) => !isPlaceholderImageUrl(s))
  if (screenshot) return screenshot
  if (!isPlaceholderImageUrl(game.image_url)) return game.image_url as string
  return fallbackCoverUrl(game.title)
}

// Both CDNs we store art from serve pre-scaled variants of the same asset, so a
// thumbnail grid never has to pull the full-resolution frame: a Steam
// screenshot drops 841 KB → 106 KB, a RAWG one 374 KB → 40 KB.
const STEAM_FULL_SEGMENT = '.1920x1080.'
const STEAM_THUMB_SEGMENT = '.600x338.'
const RAWG_MEDIA_PREFIX = 'https://media.rawg.io/media/'
const RAWG_TRANSFORM_MARKERS = ['resize/', 'crop/']
const RAWG_THUMB_WIDTH = 640

// Small variant of a gallery image. Unknown hosts, data URLs and already
// transformed RAWG paths pass through unchanged. Full-size originals stay in the
// lightbox — this is only for thumbnails.
export function thumbnailUrl(url: string): string {
  if (url.startsWith('data:')) return url
  if (url.includes(STEAM_FULL_SEGMENT)) return url.replace(STEAM_FULL_SEGMENT, STEAM_THUMB_SEGMENT)
  if (url.startsWith(RAWG_MEDIA_PREFIX)) {
    const path = url.slice(RAWG_MEDIA_PREFIX.length)
    if (RAWG_TRANSFORM_MARKERS.some((marker) => path.startsWith(marker))) return url
    return `${RAWG_MEDIA_PREFIX}resize/${RAWG_THUMB_WIDTH}/-/${path}`
  }
  return url
}

// Ordered, de-duplicated hero/gallery candidates with placeholder URLs removed.
// Falls back to the generated cover when nothing usable exists.
export function galleryImages(game: Pick<Game, 'title' | 'cover_url' | 'image_url' | 'screenshots'>): string[] {
  const ordered = [game.cover_url, ...(game.screenshots ?? []), game.image_url]
  const seen = new Set<string>()
  const result: string[] = []
  for (const url of ordered) {
    if (url && !isPlaceholderImageUrl(url) && !seen.has(url)) {
      seen.add(url)
      result.push(url)
    }
  }
  return result.length > 0 ? result : [fallbackCoverUrl(game.title)]
}

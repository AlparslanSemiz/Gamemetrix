import type { CatalogGame, GameFilters } from '../types/game'
import { DEFAULT_FILTERS, PAGE_SIZE, type ActivePage } from './config'

const CATALOG_SNAPSHOT_KEY = 'gamemetrix.catalog.snapshot.v1'
const CATALOG_SNAPSHOT_TTL_MS = 30 * 60 * 1000
const MASTHEAD_VISIBLE_SCROLL_Y = 80

export interface CatalogSnapshot {
  version: 1
  savedAt: number
  activePage: ActivePage
  activePreset: string | null
  filters: GameFilters
  games: CatalogGame[]
  catalogTotal: number
  libraryTotal: number
  viewMode: 'list' | 'grid'
  filtersOpen: boolean
  offset: number
  hasMore: boolean
  scrollY: number
  mastheadVisible: boolean
  focusedGameSlug?: string | null
  focusedGameViewportTop?: number | null
}

// performance.getEntriesByType('navigation') reflects the browser's real
// page load (reload vs. navigate) and stays fixed for the entire tab
// lifetime — it does NOT change when React Router does an in-app route
// change. So "was this browser page load a reload" is only meaningful once,
// right after that load. The capture state must live on `window`, not in a
// module variable: Vite HMR re-evaluates this module and would reset a
// module flag, making every later back-navigation look like a fresh reload
// and wrongly discard the catalog snapshot.
declare global {
  interface Window {
    /** Pathname the page was reloaded on; null = not a reload. undefined = not yet captured. */
    __gmReloadedPathAtLoad?: string | null
  }
}

// A navigation entry of type 'reload' only counts as the CURRENT load if we
// are still within the first moments of the page's time origin — a late
// capture (HMR module re-eval in a long-lived tab) must not re-trigger it.
const RELOAD_CAPTURE_WINDOW_MS = 10_000

function consumeCatalogReload(): boolean {
  if (typeof window === 'undefined') return false
  if (window.__gmReloadedPathAtLoad === undefined) {
    const [entry] = performance.getEntriesByType('navigation') as PerformanceNavigationTiming[]
    window.__gmReloadedPathAtLoad =
      entry?.type === 'reload' && performance.now() < RELOAD_CAPTURE_WINDOW_MS
        ? window.location.pathname
        : null
  }
  const reloadedPath = window.__gmReloadedPathAtLoad
  if (reloadedPath === null) return false
  window.__gmReloadedPathAtLoad = null
  // Reloading the detail page must not reset the catalog behind it —
  // only a reload on a catalog route discards the snapshot.
  return !reloadedPath.startsWith('/game')
}

export function readCatalogSnapshot(): CatalogSnapshot | null {
  if (typeof window === 'undefined') return null
  try {
    if (consumeCatalogReload()) {
      window.sessionStorage.removeItem(CATALOG_SNAPSHOT_KEY)
      return null
    }
    const raw = window.sessionStorage.getItem(CATALOG_SNAPSHOT_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<CatalogSnapshot>
    if (parsed.version !== 1 || !parsed.savedAt) return null
    if (Date.now() - parsed.savedAt > CATALOG_SNAPSHOT_TTL_MS) return null
    if (!Array.isArray(parsed.games)) return null
    const catalogTotal = parsed.catalogTotal ?? parsed.games.length
    const restoredOffset = Math.min(
      parsed.offset ?? Math.max(0, parsed.games.length - PAGE_SIZE),
      Math.max(0, parsed.games.length - PAGE_SIZE),
    )
    return {
      version: 1,
      savedAt: parsed.savedAt,
      activePage: parsed.activePage ?? 'catalog',
      activePreset: parsed.activePreset ?? null,
      filters: { ...DEFAULT_FILTERS, ...(parsed.filters ?? {}) },
      games: parsed.games,
      catalogTotal,
      libraryTotal: parsed.libraryTotal ?? 0,
      viewMode: parsed.viewMode === 'grid' ? 'grid' : 'list',
      filtersOpen: Boolean(parsed.filtersOpen),
      offset: restoredOffset,
      hasMore: (parsed.hasMore ?? false) && parsed.games.length < catalogTotal,
      scrollY: parsed.scrollY ?? 0,
      mastheadVisible: parsed.mastheadVisible ?? (parsed.scrollY ?? 0) < MASTHEAD_VISIBLE_SCROLL_Y,
      focusedGameSlug: typeof parsed.focusedGameSlug === 'string' ? parsed.focusedGameSlug : null,
      focusedGameViewportTop: typeof parsed.focusedGameViewportTop === 'number' ? parsed.focusedGameViewportTop : null,
    }
  } catch {
    return null
  }
}

const SNAPSHOT_FALLBACK_MAX_GAMES = PAGE_SIZE * 10

export function writeCatalogSnapshot(snapshot: CatalogSnapshot | null) {
  if (!snapshot) return
  const payload: CatalogSnapshot = {
    ...snapshot,
    savedAt: Date.now(),
  }
  try {
    window.sessionStorage.setItem(CATALOG_SNAPSHOT_KEY, JSON.stringify(payload))
  } catch {
    // Quota exceeded — retry with only the first pages so at least a partial
    // restore works; offset/hasMore are adjusted to stay consistent.
    try {
      const games = payload.games.slice(0, SNAPSHOT_FALLBACK_MAX_GAMES)
      window.sessionStorage.setItem(
        CATALOG_SNAPSHOT_KEY,
        JSON.stringify({
          ...payload,
          games,
          offset: Math.max(0, games.length - PAGE_SIZE),
          hasMore: true,
        }),
      )
    } catch {
      // Private mode or hard quota failure; the catalog still works normally.
    }
  }
}

export function findGameCardElement(slug: string): HTMLElement | null {
  return Array.from(document.querySelectorAll<HTMLElement>('[data-game-slug]'))
    .find((element) => element.dataset.gameSlug === slug) ?? null
}

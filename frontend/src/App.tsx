/* eslint-disable react-hooks/set-state-in-effect */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import {
  Bell,
  CheckCircle2,
  ArrowDown,
  ArrowUp,
  Compass,
  Gift,
  Grid2X2,
  Home,
  Info,
  List,
  LogIn,
  MoreHorizontal,
  Search,
  Settings,
  SlidersHorizontal,
  Tag,
  UserRound,
} from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'
import './App.css'
import { AlertsPanel } from './components/AlertsPanel'
import { FilterBar } from './components/FilterBar'
import { GameCard } from './components/GameCard'
import { RatingExplainer } from './components/RatingExplainer'
import { TrailerModal } from './components/TrailerModal'
import {
  getFacets,
  getGameTrailer,
  getGames,
  getIntegrationStatus,
} from './services/games'
import type { CollectionKey } from './state/collections'
import { trackProductEvent } from './services/analytics'
import { useAccount } from './state/useAccount'
import { useCollections } from './state/useCollections'
import type { Facets, Game, GameFilters, GameSort, ProviderStatus } from './types/game'

type MainPage = 'catalog' | 'watchlist' | 'playing' | 'seen' | 'completed' | 'liked' | 'favorites' | 'suggestions'
export type UtilityPage = 'alerts' | 'settings' | 'about'
type ActivePage = MainPage | UtilityPage

const ROUTABLE_MAIN_PAGES = new Set<MainPage>(['watchlist', 'suggestions'])

const CURRENT_YEAR = new Date().getFullYear()
const PAGE_SIZE = 24
const CATALOG_SNAPSHOT_KEY = 'gamemetrix.catalog.snapshot.v1'
const CATALOG_SNAPSHOT_TTL_MS = 30 * 60 * 1000

interface CatalogSnapshot {
  version: 1
  savedAt: number
  activePage: ActivePage
  activePreset: string | null
  filters: GameFilters
  games: Game[]
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

interface CuratedPreset {
  id: string
  label: string
  icon: typeof Search
  filters: Partial<GameFilters>
}

interface SidebarGroup {
  label: string
  items: CuratedPreset[]
}

const SIDEBAR_GROUPS: SidebarGroup[] = [
  {
    label: 'Deals',
    items: [
      {
        id: 'best-deals',
        label: 'Best Deals',
        icon: Tag,
        filters: { dealMode: 'best', minScore: 75, minLiveSources: 1, sort: 'rank_score', direction: 'desc' },
      },
      {
        id: 'free-games',
        label: 'Free Games',
        icon: Gift,
        filters: { dealMode: 'free', sort: 'rank_score', direction: 'desc' },
      },
    ],
  },
]

function findPreset(id: string): CuratedPreset | undefined {
  for (const group of SIDEBAR_GROUPS) {
    const found = group.items.find((p) => p.id === id)
    if (found) return found
  }
  return undefined
}

const BEST_OF_YEAR_RANGE = Array.from(
  { length: CURRENT_YEAR - 2019 },
  (_, i) => CURRENT_YEAR - i,
).reverse()

const DEFAULT_FILTERS: GameFilters = {
  q: '',
  genre: '',
  platform: '',
  developer: '',
  publisher: '',
  yearMin: 1970,
  yearMax: CURRENT_YEAR,
  minScore: 0,
  maxScore: 100,
  minRatings: 0,
  maxRatings: 0,
  minLiveSources: 0,
  requireCritic: false,
  hasAward: false,
  dealMode: 'all',
  playerMode: '',
  playtimeMinHours: null,
  playtimeMaxHours: null,
  sort: 'rank_score',
  direction: 'desc',
}

// Deep-link support: developer / genre / year passed as URL query params on the
// catalog land on a pre-filtered homepage (used by the game detail page links).
function readUrlFilters(search: string): Partial<GameFilters> {
  const params = new URLSearchParams(search)
  const next: Partial<GameFilters> = {}
  const genre = params.get('genre')?.trim()
  const developer = params.get('developer')?.trim()
  const year = Number(params.get('year'))
  if (genre) next.genre = genre
  if (developer) next.developer = developer
  if (Number.isInteger(year) && year > 1970 && year <= CURRENT_YEAR) {
    next.yearMin = year
    next.yearMax = year
  }
  return next
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
const useIsomorphicLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect

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

function readCatalogSnapshot(): CatalogSnapshot | null {
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
      mastheadVisible: parsed.mastheadVisible ?? (parsed.scrollY ?? 0) < 80,
      focusedGameSlug: typeof parsed.focusedGameSlug === 'string' ? parsed.focusedGameSlug : null,
      focusedGameViewportTop: typeof parsed.focusedGameViewportTop === 'number' ? parsed.focusedGameViewportTop : null,
    }
  } catch {
    return null
  }
}

function findGameCardElement(slug: string): HTMLElement | null {
  return Array.from(document.querySelectorAll<HTMLElement>('[data-game-slug]'))
    .find((element) => element.dataset.gameSlug === slug) ?? null
}

// Detail-page visits persist screenshots/DLC/similar-game data that the list
// endpoint then echoes back — those blobs are useless to the catalog cards but
// can push a multi-page snapshot past the sessionStorage quota, silently
// killing scroll restoration. Strip them before saving.
const SNAPSHOT_SUMMARY_MAX_CHARS = 460

function compactText(value: string, maxLength: number): string {
  return value.length > maxLength ? `${value.slice(0, maxLength).trimEnd()}...` : value
}

function compactGameForSnapshot(game: Game): Game {
  return {
    ...game,
    summary: compactText(game.summary, SNAPSHOT_SUMMARY_MAX_CHARS),
    summary_short: game.summary_short
      ? compactText(game.summary_short, SNAPSHOT_SUMMARY_MAX_CHARS)
      : compactText(game.summary, SNAPSHOT_SUMMARY_MAX_CHARS),
    source_scores: game.source_scores.map(({ source, score, scale, status, review_count }) => ({
      source,
      score,
      scale,
      status,
      review_count,
    })),
    awards: game.awards.slice(0, 12),
    screenshots: [],
    system_requirements: [],
    dlcs: [],
    similar_games: [],
    price_snapshots: [],
  }
}

const SNAPSHOT_FALLBACK_MAX_GAMES = PAGE_SIZE * 10

function writeCatalogSnapshot(snapshot: CatalogSnapshot | null) {
  if (!snapshot) return
  const payload: CatalogSnapshot = {
    ...snapshot,
    games: snapshot.games.map(compactGameForSnapshot),
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

const mainNavItems: Array<{ id: MainPage; label: string; icon: typeof Search }> = [
  { id: 'catalog', label: 'Home', icon: Home },
  { id: 'watchlist', label: 'Wishlist', icon: CheckCircle2 },
  { id: 'suggestions', label: 'For You', icon: Compass },
]

const utilityNavItems: Array<{ id: UtilityPage; label: string; icon: typeof Search }> = [
  { id: 'settings', label: 'Settings', icon: Settings },
  { id: 'alerts', label: 'Alerts', icon: Bell },
  { id: 'about', label: 'About', icon: Info },
]

const mobileNavItems: Array<{ id: MainPage | 'alerts'; label: string; icon: typeof Search }> = [
  { id: 'catalog', label: 'Home', icon: Home },
  { id: 'watchlist', label: 'Wishlist', icon: CheckCircle2 },
  { id: 'suggestions', label: 'For You', icon: Compass },
  { id: 'alerts', label: 'Alerts', icon: Bell },
]

const collectionLabels: Record<CollectionKey, string> = {
  watchlist: 'Wishlist',
  playing: 'Playing',
  seen: 'Played',
  completed: 'Completed',
  liked: 'Liked',
  favorites: 'Favorites',
}

const collectionPageMap: Partial<Record<MainPage, CollectionKey>> = {
  watchlist: 'watchlist',
  playing: 'playing',
  seen: 'seen',
  completed: 'completed',
  liked: 'liked',
  favorites: 'favorites',
}

const sortOptions: Array<{ label: string; value: GameSort }> = [
  { label: 'GameMetrix Rank', value: 'rank_score' },
  { label: 'Raw Score', value: 'metrix_score' },
  { label: 'Date Released', value: 'release_year' },
  { label: 'Critic Rating', value: 'critic_score' },
  { label: 'User Rating', value: 'user_score' },
  { label: 'Metacritic Rating', value: 'metacritic_score' },
  { label: 'OpenCritic Rating', value: 'opencritic_score' },
  { label: 'Steam Rating', value: 'steam_score' },
  { label: 'No. Ratings', value: 'review_count' },
  { label: 'Title', value: 'title' },
]

function formatRoundedThousands(value: number): string {
  if (value >= 1000) return `${Math.round(value / 1000)}K`
  return new Intl.NumberFormat('en-US').format(value)
}

interface AppContentProps {
  initialGames?: Game[]
  initialTotal?: number
  initialPage?: UtilityPage
}

function catalogFilterSignature(filters: GameFilters, pendingApply: number): string {
  return JSON.stringify([
    filters.q,
    filters.genre,
    filters.platform,
    filters.developer,
    filters.publisher,
    filters.minRatings,
    filters.minLiveSources,
    filters.requireCritic,
    filters.sort,
    filters.direction,
    pendingApply,
  ])
}

export function AppContent({ initialGames = [], initialTotal = 0, initialPage }: AppContentProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const requestedView = new URLSearchParams(location.search).get('view') as MainPage | null
  const routeInitialPage: ActivePage = initialPage
    ?? (requestedView && ROUTABLE_MAIN_PAGES.has(requestedView) ? requestedView : 'catalog')
  // Seeded once at mount: a deep link like /?developer=Larian arrives from a
  // detail-page link and must apply its filter instead of the curated home list.
  const urlFilters = readUrlFilters(location.search)
  const hasUrlFilters = Object.keys(urlFilters).length > 0
  const [restoredSnapshot, setRestoredSnapshot] = useState<CatalogSnapshot | null>(null)
  const [activePage, setActivePage] = useState<ActivePage>(routeInitialPage)
  const [games, setGames] = useState<Game[]>(hasUrlFilters ? [] : initialGames)
  const [facets, setFacets] = useState<Facets>({ genres: [], years: [], platforms: [], developers: [] })
  const [filters, setFilters] = useState<GameFilters>(() => ({ ...DEFAULT_FILTERS, ...urlFilters }))
  const [pendingApply, setPendingApply] = useState(0)
  const { collections, toggleCollection } = useCollections()
  const { account, syncCollection } = useAccount()
  const [providerStatuses, setProviderStatuses] = useState<ProviderStatus[]>([])
  const [catalogTotal, setCatalogTotal] = useState(initialTotal)
  const [libraryTotal, setLibraryTotal] = useState(initialTotal)
  const [isLoading, setIsLoading] = useState(hasUrlFilters || initialGames.length === 0)
  const [trailerGame, setTrailerGame] = useState<Game | null>(null)
  const [trailerVideoId, setTrailerVideoId] = useState<string | null>(null)
  const [isTrailerLoading, setIsTrailerLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'list' | 'grid'>('list')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [activePreset, setActivePreset] = useState<string | null>(null)
  const [mobileMoreOpen, setMobileMoreOpen] = useState(false)
  const [mastheadVisible, setMastheadVisible] = useState(true)
  const [fetchKey, setFetchKey] = useState(0)
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(!hasUrlFilters && initialGames.length < initialTotal)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const loaderRef = useRef<HTMLDivElement>(null)
  const mastheadRef = useRef<HTMLElement>(null)
  const lastScrollYRef = useRef(0)
  const mastheadVisibleRef = useRef(true)
  const scrollDirectionRef = useRef<{ sign: -1 | 0 | 1; distance: number }>({ sign: 0, distance: 0 })
  const scrollFrameRef = useRef<number | null>(null)
  const topScrollFrameRef = useRef<number | null>(null)
  const topScrollCleanupRef = useRef<(() => void) | null>(null)
  const latestCatalogRef = useRef<CatalogSnapshot | null>(null)
  const snapshotAnchorRef = useRef<{ slug: string; viewportTop: number } | null>(null)
  // Holds the `${fetchKey}:${offset}` pair the games list currently reflects;
  // pre-seeded on snapshot restore so the mount run keeps the restored list.
  const lastFetchSignatureRef = useRef<string | null>(
    initialGames.length && !hasUrlFilters ? '0:0' : null,
  )
  // Always up to date with latest filters without being a dep of the load effect
  const filtersRef = useRef(filters)
  const lastFilterResetSignatureRef = useRef(catalogFilterSignature(filters, pendingApply))
  // Prefetch cache: holds the already-fetched next page so scroll is instant
  const prefetchRef = useRef<{ offset: number; games: Game[]; total: number } | null>(null)

  useIsomorphicLayoutEffect(() => {
    if (routeInitialPage !== 'catalog') return
    // A URL filter deep link (/?genre=…) must win over a stale catalog snapshot.
    if (hasUrlFilters) return
    const snapshot = readCatalogSnapshot()
    if (!snapshot?.games.length) return

    filtersRef.current = snapshot.filters
    lastFilterResetSignatureRef.current = catalogFilterSignature(snapshot.filters, pendingApply)
    lastFetchSignatureRef.current = `0:${snapshot.offset}`
    lastScrollYRef.current = snapshot.scrollY
    mastheadVisibleRef.current = snapshot.mastheadVisible
    snapshotAnchorRef.current = snapshot.focusedGameSlug && typeof snapshot.focusedGameViewportTop === 'number'
      ? { slug: snapshot.focusedGameSlug, viewportTop: snapshot.focusedGameViewportTop }
      : null

    setActivePage(snapshot.activePage)
    setActivePreset(snapshot.activePreset)
    setFilters(snapshot.filters)
    setGames(snapshot.games)
    setCatalogTotal(snapshot.catalogTotal)
    setLibraryTotal(snapshot.libraryTotal)
    setViewMode(snapshot.viewMode)
    setFiltersOpen(snapshot.filtersOpen)
    setOffset(snapshot.offset)
    setHasMore(snapshot.hasMore)
    setMastheadVisible(snapshot.mastheadVisible)
    setIsLoading(false)
    setRestoredSnapshot(snapshot)
  }, [routeInitialPage])

  useEffect(() => {
    filtersRef.current = filters
  }, [filters])

  useEffect(() => {
    latestCatalogRef.current = {
      version: 1,
      savedAt: Date.now(),
      activePage,
      activePreset,
      filters,
      games,
      catalogTotal,
      libraryTotal,
      viewMode,
      filtersOpen,
      offset,
      hasMore,
      scrollY: window.scrollY,
      mastheadVisible,
      focusedGameSlug: snapshotAnchorRef.current?.slug ?? null,
      focusedGameViewportTop: snapshotAnchorRef.current?.viewportTop ?? null,
    }
  }, [activePage, activePreset, catalogTotal, filters, filtersOpen, games, hasMore, libraryTotal, mastheadVisible, offset, viewMode])

  const saveCatalogSnapshot = useCallback((focusedGame?: Game) => {
    const snapshot = latestCatalogRef.current
    if (!snapshot) return
    const scrollY = window.scrollY

    if (focusedGame) {
      const card = findGameCardElement(focusedGame.slug)
      snapshotAnchorRef.current = {
        slug: focusedGame.slug,
        viewportTop: card?.getBoundingClientRect().top ?? 0,
      }
    }

    lastScrollYRef.current = scrollY
    writeCatalogSnapshot({
      ...snapshot,
      scrollY,
      mastheadVisible: mastheadVisibleRef.current,
      focusedGameSlug: snapshotAnchorRef.current?.slug ?? null,
      focusedGameViewportTop: snapshotAnchorRef.current?.viewportTop ?? null,
    })
  }, [])

  useEffect(() => {
    // Uses lastScrollYRef (updated on every real scroll event) rather than
    // reading window.scrollY at save time: on SPA navigation away, the
    // catalog DOM is removed before this cleanup runs, which clamps
    // window.scrollY to 0 and would otherwise persist a bogus position.
    const saveSnapshot = () => {
      const snapshot = latestCatalogRef.current
      if (!snapshot) return
      writeCatalogSnapshot({
        ...snapshot,
        scrollY: lastScrollYRef.current,
        mastheadVisible: mastheadVisibleRef.current,
        focusedGameSlug: snapshotAnchorRef.current?.slug ?? null,
        focusedGameViewportTop: snapshotAnchorRef.current?.viewportTop ?? null,
      })
    }
    const previousScrollRestoration = window.history.scrollRestoration
    window.history.scrollRestoration = 'manual'
    window.addEventListener('pagehide', saveSnapshot)
    return () => {
      // Also fires on SPA navigation away (e.g. to /game/:slug), unlike
      // pagehide which only fires on full unload/refresh.
      saveSnapshot()
      window.removeEventListener('pagehide', saveSnapshot)
      window.history.scrollRestoration = previousScrollRestoration
    }
  }, [])

  // useLayoutEffect runs synchronously after DOM commit but before the
  // browser paints, so the scroll position is applied before the user
  // ever sees a scrollY=0 frame — avoiding the top-then-jump flash a
  // regular useEffect (which runs after paint) would cause. The global
  // `scroll-behavior: smooth` (index.css) must be suspended here too,
  // otherwise the jump itself animates over ~300ms and reproduces the
  // same flash.
  useIsomorphicLayoutEffect(() => {
    const snapshot = restoredSnapshot
    if (!snapshot?.games.length) return
    mastheadVisibleRef.current = snapshot.mastheadVisible

    const restorePosition = () => {
      let nextScrollY = snapshot.scrollY
      if (snapshot.focusedGameSlug && typeof snapshot.focusedGameViewportTop === 'number') {
        const card = findGameCardElement(snapshot.focusedGameSlug)
        if (card) {
          nextScrollY = window.scrollY + card.getBoundingClientRect().top - snapshot.focusedGameViewportTop
        }
      }

      const previousBehavior = document.documentElement.style.scrollBehavior
      document.documentElement.style.scrollBehavior = 'auto'
      window.scrollTo(0, Math.max(0, nextScrollY))
      document.documentElement.style.scrollBehavior = previousBehavior
      lastScrollYRef.current = window.scrollY
    }

    restorePosition()
    const restoreFrameIds: number[] = []
    const firstFrame = window.requestAnimationFrame(() => {
      restorePosition()
      const secondFrame = window.requestAnimationFrame(restorePosition)
      restoreFrameIds.push(secondFrame)
    })
    restoreFrameIds.push(firstFrame)
    const settleTimer = window.setTimeout(restorePosition, 80)

    return () => {
      restoreFrameIds.forEach((frameId) => window.cancelAnimationFrame(frameId))
      window.clearTimeout(settleTimer)
    }
  }, [restoredSnapshot])

  useEffect(() => {
    let active = true
    async function loadFacets() {
      try {
        const nextFacets = await getFacets()
        if (active) setFacets(nextFacets)
      } catch {
        if (active) setError('Backend facets could not be loaded.')
      }
    }
    void loadFacets()
    void getGames(DEFAULT_FILTERS, 1, 0)
      .then((response) => {
        if (active) setLibraryTotal(response.total)
      })
      .catch(() => undefined)
    void getIntegrationStatus().then(setProviderStatuses).catch(() => undefined)
    return () => { active = false }
  }, [])

  // Filter deps → reset to page 0, clear prefetch cache, and bump the fetch key.
  // Skip-by-signature instead of a consumable flag: the effect only acts when
  // the dependency values actually differ from the last run it acted on, so
  // the mount run (fresh or snapshot-restored) and StrictMode's replay are
  // both no-ops without poisoning later, genuine dependency changes.
  const filterResetSignature = catalogFilterSignature(filters, pendingApply)
  useEffect(() => {
    if (lastFilterResetSignatureRef.current === filterResetSignature) return
    lastFilterResetSignatureRef.current = filterResetSignature
    prefetchRef.current = null
    setOffset(0)
    setFetchKey((k) => k + 1)
  }, [filterResetSignature])

  // Actual fetch — triggered by fetchKey (filter change) or offset (scroll).
  // On a snapshot-restored mount the ref already holds the restored page's
  // signature, so the games on screen are kept instead of being refetched.
  // An aborted run (StrictMode replay, rapid dep change) clears the ref so
  // the next run with the same signature fetches for real.
  useEffect(() => {
    if (offset > 0 && catalogTotal > 0 && offset >= catalogTotal) {
      setHasMore(false)
      setIsLoadingMore(false)
      return
    }
    const fetchSignature = `${fetchKey}:${offset}`
    if (lastFetchSignatureRef.current === fetchSignature) return
    lastFetchSignatureRef.current = fetchSignature
    let active = true
    let settled = false
    const f = filtersRef.current
    const isFirst = offset === 0
    if (isFirst) {
      setIsLoading(true)
      setGames([])
    } else {
      setIsLoadingMore(true)
    }
    setError(null)

    function applyPage(games: Game[], total: number) {
      settled = true
      if (!active) return
      if (isFirst) {
        setGames(games)
      } else {
        setGames((prev) => [...prev, ...games])
      }
      setCatalogTotal(total)
      const newCount = offset + games.length
      setHasMore(games.length > 0 && newCount < total)
      if (isFirst) setIsLoading(false)
      else setIsLoadingMore(false)
      // Prefetch the next page in the background
      const nextOffset = newCount
      if (games.length > 0 && nextOffset < total) {
        getGames(f, PAGE_SIZE, nextOffset).then((prefetched) => {
          if (active) {
            prefetchRef.current = { offset: nextOffset, games: prefetched.games, total: prefetched.total }
          }
        }).catch(() => {})
      }
    }

    async function loadGames() {
      // Serve from prefetch cache when offset matches
      const cached = prefetchRef.current
      if (!isFirst && cached && cached.offset === offset) {
        prefetchRef.current = null
        applyPage(cached.games, cached.total)
        return
      }
      try {
        const response = await getGames(f, PAGE_SIZE, offset)
        applyPage(response.games, response.total)
      } catch {
        settled = true
        if (active) {
          if (isFirst) {
            setGames([])
            setIsLoading(false)
          } else {
            setIsLoadingMore(false)
          }
          setError('GameMetrix API is not reachable yet.')
        }
      }
    }
    void loadGames()
    return () => {
      active = false
      if (!settled) lastFetchSignatureRef.current = null
    }
  }, [catalogTotal, fetchKey, offset])

  // IntersectionObserver — load next page when sentinel enters viewport
  useEffect(() => {
    const el = loaderRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && hasMore && !isLoadingMore && !isLoading) {
          setOffset((prev) => {
            const next = prev + PAGE_SIZE
            if (catalogTotal > 0 && prev >= Math.max(0, catalogTotal - PAGE_SIZE)) {
              return prev
            }
            return next
          })
        }
      },
      { rootMargin: '300px' },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [catalogTotal, hasMore, isLoadingMore, isLoading])

  useEffect(() => {
    lastScrollYRef.current = window.scrollY

    const setVisible = (next: boolean) => {
      if (mastheadVisibleRef.current === next) return
      mastheadVisibleRef.current = next
      setMastheadVisible(next)
    }

    function handleScroll() {
      if (scrollFrameRef.current !== null) return
      scrollFrameRef.current = window.requestAnimationFrame(() => {
        const currentY = window.scrollY
        const delta = currentY - lastScrollYRef.current
        const activeElement = document.activeElement

        if (mastheadRef.current?.contains(activeElement)) {
          setVisible(true)
          scrollDirectionRef.current = { sign: 0, distance: 0 }
        } else if (currentY < 96) {
          setVisible(true)
          scrollDirectionRef.current = { sign: 0, distance: 0 }
        } else if (Math.abs(delta) > 1) {
          const sign = delta > 0 ? 1 : -1
          const currentDirection = scrollDirectionRef.current
          const distance = currentDirection.sign === sign
            ? currentDirection.distance + Math.abs(delta)
            : Math.abs(delta)

          scrollDirectionRef.current = { sign, distance }

          if (sign > 0 && distance > 64) {
            setVisible(false)
            scrollDirectionRef.current = { sign, distance: 0 }
          } else if (sign < 0 && distance > 42) {
            setVisible(true)
            scrollDirectionRef.current = { sign, distance: 0 }
          }
        }

        lastScrollYRef.current = currentY
        scrollFrameRef.current = null
      })
    }

    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', handleScroll)
      if (scrollFrameRef.current !== null) {
        window.cancelAnimationFrame(scrollFrameRef.current)
      }
    }
  }, [])

  const collectionSets = useMemo(() => ({
    watchlist: new Set(collections.watchlist),
    playing: new Set(collections.playing),
    seen: new Set(collections.seen),
    completed: new Set(collections.completed),
    liked: new Set(collections.liked),
    favorites: new Set(collections.favorites),
  }), [collections])

  const handleToggleCollection = useCallback((collection: CollectionKey, slug: string) => {
    const enabled = !collectionSets[collection].has(slug)
    toggleCollection(collection, slug)
    void syncCollection(collection, slug, enabled).catch(() => {
      setError('This collection change is saved locally, but account sync is temporarily unavailable.')
    })
    if (collection === 'watchlist' && enabled) {
      trackProductEvent('wishlist_add', { game_slug: slug })
    }
  }, [collectionSets, syncCollection, toggleCollection])

  const visibleGames = useMemo(() => {
    if (activePage === 'suggestions') {
      const excluded = new Set([
        ...collections.seen,
        ...collections.completed,
        ...collections.favorites,
        ...collections.liked,
      ])
      return games
        .filter((g) => !excluded.has(g.slug))
        .sort((a, b) => b.metrix_score - a.metrix_score)
    }
    const collectionKey = collectionPageMap[activePage as MainPage]
    if (!collectionKey) return games
    const allowed = new Set(collections[collectionKey])
    return games.filter((g) => allowed.has(g.slug))
  }, [activePage, collections, games])

  const pageTitle = useMemo(() => {
    if (activePreset === 'best-of-year') {
      const year = filters.yearMin
      return year === CURRENT_YEAR ? `Best of ${year} · So Far` : `Best of ${year}`
    }
    if (activePage in collectionLabels) return collectionLabels[activePage as CollectionKey]
    if (activePage === 'catalog') return 'Catalog'
    if (activePage === 'suggestions') return 'Discover'
    return utilityNavItems.find((item) => item.id === activePage)?.label ?? 'GameMetrix'
  }, [activePage, activePreset, filters.yearMin])

  const readyProviders = providerStatuses.filter((p) => p.status === 'ready').length

  const handleOpenTrailer = useCallback(async (game: Game) => {
    setTrailerGame(game)
    setTrailerVideoId(null)
    setIsTrailerLoading(true)
    try {
      const trailer = await getGameTrailer(game.slug)
      setTrailerVideoId(trailer.video_id)
    } catch {
      setTrailerVideoId(null)
    } finally {
      setIsTrailerLoading(false)
    }
  }, [])

  const handleFilterDeveloper = useCallback((developer: string) => {
    setActivePage('catalog')
    setFilters((p) => ({ ...p, developer, publisher: '' }))
  }, [])

  const handleFilterPublisher = useCallback((publisher: string) => {
    setActivePage('catalog')
    setFilters((p) => ({ ...p, publisher, developer: '' }))
  }, [])

  const handleFilterGenre = useCallback((genre: string) => {
    setActivePage('catalog')
    setFilters((p) => ({ ...p, genre }))
  }, [])

  const cancelTopScroll = useCallback(() => {
    if (topScrollFrameRef.current !== null) {
      window.cancelAnimationFrame(topScrollFrameRef.current)
      topScrollFrameRef.current = null
    }
    topScrollCleanupRef.current?.()
    topScrollCleanupRef.current = null
    lastScrollYRef.current = window.scrollY
  }, [])

  useEffect(() => () => cancelTopScroll(), [cancelTopScroll])

  const scrollCatalogToTop = useCallback(() => {
    cancelTopScroll()
    snapshotAnchorRef.current = null
    mastheadVisibleRef.current = true
    scrollDirectionRef.current = { sign: 0, distance: 0 }
    setMastheadVisible(true)
    const startY = window.scrollY
    if (startY <= 0) {
      lastScrollYRef.current = 0
      window.scrollTo(0, 0)
      return
    }

    const startedAt = performance.now()
    const duration = Math.min(1200, Math.max(420, startY * 0.4))
    const previousBehavior = document.documentElement.style.scrollBehavior
    document.documentElement.style.scrollBehavior = 'auto'

    const interruptEvents = ['wheel', 'touchstart', 'pointerdown', 'keydown'] as const
    const cleanup = () => {
      interruptEvents.forEach((eventName) => {
        window.removeEventListener(eventName, cancelTopScroll)
      })
      document.documentElement.style.scrollBehavior = previousBehavior
    }
    topScrollCleanupRef.current = cleanup
    interruptEvents.forEach((eventName) => {
      window.addEventListener(eventName, cancelTopScroll, { passive: true })
    })

    const finish = () => {
      topScrollFrameRef.current = null
      topScrollCleanupRef.current?.()
      topScrollCleanupRef.current = null
    }

    const step = (now: number) => {
      const progress = Math.min(1, (now - startedAt) / duration)
      const eased = 1 - Math.pow(1 - progress, 3)
      const nextY = Math.max(0, Math.round(startY * (1 - eased)))

      window.scrollTo(0, nextY)
      lastScrollYRef.current = window.scrollY

      if (progress < 1 && window.scrollY > 0) {
        topScrollFrameRef.current = window.requestAnimationFrame(step)
        return
      }

      window.scrollTo(0, 0)
      lastScrollYRef.current = 0
      finish()
    }

    topScrollFrameRef.current = window.requestAnimationFrame(step)
  }, [cancelTopScroll])

  const goHome = () => {
    if (location.pathname !== '/' || location.search) navigate('/')
    scrollCatalogToTop()
    setActivePage('catalog')
    setFilters(DEFAULT_FILTERS)
    setActivePreset(null)
    setPendingApply((n) => n + 1)
  }

  const applyPreset = (preset: CuratedPreset) => {
    setActivePage('catalog')
    setActivePreset(preset.id)
    if (preset.id === 'best-of-year') {
      setFilters({ ...DEFAULT_FILTERS, yearMin: CURRENT_YEAR, yearMax: CURRENT_YEAR, sort: 'rank_score', direction: 'desc' })
    } else {
      setFilters({ ...DEFAULT_FILTERS, ...preset.filters })
    }
    setPendingApply((n) => n + 1)
  }

  const openPreset = (preset: CuratedPreset) => {
    if (preset.id === 'best-deals') {
      navigate('/deals')
      return
    }
    if (preset.id === 'free-games') {
      navigate('/best/free-pc-games')
      return
    }
    applyPreset(preset)
  }

  const selectBestOfYear = (year: number) => {
    setFilters((prev) => ({ ...prev, yearMin: year, yearMax: year }))
    setPendingApply((n) => n + 1)
  }

  const clearFilter = (key: 'developer' | 'publisher' | 'genre' | 'platform') => {
    setFilters((current) => ({ ...current, [key]: '' }))
  }

  const openMainPage = (id: MainPage) => {
    setActivePage(id)
    setActivePreset(null)
    const target = id === 'catalog' ? '/' : `/?view=${encodeURIComponent(id)}`
    if (`${location.pathname}${location.search}` !== target) navigate(target)
  }

  const openUtilityPage = (id: UtilityPage) => {
    setMobileMoreOpen(false)
    if (location.pathname !== `/${id}`) navigate(`/${id}`)
  }

  const isUtilityPage = utilityNavItems.some((item) => item.id === activePage)

  return (
    <main className="app-shell">
      <aside className="side-rail" aria-label="Workspace navigation">
        <div className="rail-top">
          <div className="rail-group">
            {mainNavItems.map(({ icon: Icon, id, label }) => (
              <button
                type="button"
                className={activePage === id && activePreset === null ? 'is-active' : ''}
                key={id}
                title={label}
                onClick={() => openMainPage(id)}
              >
                <Icon size={22} aria-hidden="true" />
                <span>{label}</span>
              </button>
            ))}
          </div>
          {SIDEBAR_GROUPS.map((group) => (
            <div key={group.label}>
              <div className="rail-divider" />
              <div className="rail-group rail-group-curated">
                <span className="rail-section-label">{group.label}</span>
                {group.items.map((preset) => {
                  const Icon = preset.icon
                  return (
                    <button
                      type="button"
                      className={activePreset === preset.id ? 'is-active' : ''}
                      key={preset.id}
                      title={preset.label}
                      onClick={() => openPreset(preset)}
                    >
                      <Icon size={18} aria-hidden="true" />
                      <span>{preset.label}</span>
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
        <div className="rail-group rail-utility-group">
          <button type="button" title={account ? 'Account' : 'Login'} onClick={() => navigate(account ? '/account' : '/login')}>
            {account ? <UserRound size={22} aria-hidden="true" /> : <LogIn size={22} aria-hidden="true" />}
            <span>{account ? 'Account' : 'Login'}</span>
          </button>
          {utilityNavItems.map(({ icon: Icon, id, label }) => (
            <button
              type="button"
              className={activePage === id ? 'is-active' : ''}
              key={id}
              title={label}
              onClick={() => openUtilityPage(id)}
            >
              <Icon size={22} aria-hidden="true" />
              <span>{label}</span>
            </button>
          ))}
        </div>
      </aside>

      <nav className="mobile-tabbar" aria-label="Mobile navigation">
        {mobileNavItems.map(({ icon: Icon, id, label }) => (
          <button
            type="button"
            className={activePage === id && (id !== 'catalog' || activePreset === null) ? 'is-active' : ''}
            key={id}
            onClick={() => {
              if (id === 'alerts') openUtilityPage(id)
              else openMainPage(id)
            }}
          >
            <Icon size={20} aria-hidden="true" />
            <span>{label}</span>
          </button>
        ))}
        <button type="button" className={mobileMoreOpen ? 'is-active' : ''} onClick={() => setMobileMoreOpen((open) => !open)} aria-expanded={mobileMoreOpen}>
          <MoreHorizontal size={20} aria-hidden="true" />
          <span>More</span>
        </button>
        {mobileMoreOpen ? (
          <div className="mobile-more-menu">
            <button type="button" onClick={() => navigate(account ? '/account' : '/login')}>
              {account ? <UserRound size={18} /> : <LogIn size={18} />}{account ? 'Account' : 'Login'}
            </button>
            <button type="button" onClick={() => openUtilityPage('settings')}><Settings size={18} />Settings</button>
            <button type="button" onClick={() => openUtilityPage('about')}><Info size={18} />About</button>
          </div>
        ) : null}
      </nav>

      <section className={`workspace ${mastheadVisible ? 'masthead-open' : 'masthead-collapsed'}`}>
        <header ref={mastheadRef} className={`masthead ${mastheadVisible ? 'is-visible' : 'is-hidden'}`}>
          <button type="button" className="brand" onClick={goHome}>
            <img src="/favicon.svg" alt="" className="brand-icon" aria-hidden="true" />
            <span className="brand-text">
              Game<span className="brand-accent">Metrix</span>
            </span>
          </button>
          <div className="masthead-search">
            <input
              type="search"
              placeholder="Title Search"
              maxLength={120}
              value={filters.q}
              onFocus={() => {
                mastheadVisibleRef.current = true
                setMastheadVisible(true)
              }}
              onChange={(e) => setFilters((p) => ({ ...p, q: e.target.value }))}
              aria-label="Search games by title"
            />
            <div className="masthead-search-meta">
              <span>{formatRoundedThousands(libraryTotal || catalogTotal)} games</span>
              <Search size={18} aria-hidden="true" />
            </div>
          </div>
        </header>

        <div className="provider-strip">
          <span>{visibleGames.length} shown</span>
          <span>{games.length} / {catalogTotal || games.length} loaded</span>
          <span>{readyProviders} / {providerStatuses.length || 5} providers ready</span>
        </div>

        {isUtilityPage ? (
          <section className="utility-panel">
            <h1>{pageTitle}</h1>
            {activePage === 'settings' ? (
              <div className="settings-grid">
                <section className="settings-card">
                  <h2>Catalog Layout</h2>
                  <div className="settings-segmented" role="group" aria-label="Catalog layout">
                    <button
                      type="button"
                      className={viewMode === 'list' ? 'is-active' : ''}
                      onClick={() => setViewMode('list')}
                    >
                      <List size={16} aria-hidden="true" />
                      <span>List</span>
                    </button>
                    <button
                      type="button"
                      className={viewMode === 'grid' ? 'is-active' : ''}
                      onClick={() => setViewMode('grid')}
                    >
                      <Grid2X2 size={16} aria-hidden="true" />
                      <span>Grid</span>
                    </button>
                  </div>
                </section>
                <section className="settings-card">
                  <h2>Filter Panel</h2>
                  <div className="settings-segmented" role="group" aria-label="Filter panel">
                    <button
                      type="button"
                      className={filtersOpen ? 'is-active' : ''}
                      onClick={() => setFiltersOpen(true)}
                    >
                      <SlidersHorizontal size={16} aria-hidden="true" />
                      <span>Open</span>
                    </button>
                    <button
                      type="button"
                      className={!filtersOpen ? 'is-active' : ''}
                      onClick={() => setFiltersOpen(false)}
                    >
                      <List size={16} aria-hidden="true" />
                      <span>Compact</span>
                    </button>
                  </div>
                </section>
              </div>
            ) : activePage === 'alerts' ? (
              <AlertsPanel watchlistSlugs={collections.watchlist} />
            ) : activePage === 'about' ? (
              <RatingExplainer />
            ) : null}
          </section>
        ) : (
          <section className="catalog" id="catalog">
            {activePage === 'catalog' && activePreset === null ? (
              <div className="page-heading page-heading-catalog">
                <h1>Game rankings</h1>
                <p>Four-source ratings with current compatibility, playtime and price context.</p>
              </div>
            ) : null}
            {(activePage !== 'catalog' || activePreset !== null) && (
              <div className="page-heading">
                <h1>
                  {activePreset === 'best-of-year'
                    ? pageTitle
                    : activePreset !== null
                      ? (findPreset(activePreset)?.label ?? pageTitle)
                      : pageTitle}
                </h1>
                {activePreset === 'best-of-year' && (
                  <div className="year-picker" role="group" aria-label="Select year">
                    {BEST_OF_YEAR_RANGE.map((year) => (
                      <button
                        key={year}
                        type="button"
                        className={filters.yearMin === year ? 'is-active' : ''}
                        onClick={() => selectBestOfYear(year)}
                      >
                        {year === CURRENT_YEAR ? `${year} · So Far` : String(year)}
                      </button>
                    ))}
                  </div>
                )}
                <p>
                  {activePreset === 'best-of-year'
                    ? filters.yearMin === CURRENT_YEAR
                      ? `Year in progress — ranked by reliability-weighted score as of ${new Date().toLocaleString('en', { month: 'long', year: 'numeric' })}.`
                      : `Ranked by reliability-weighted score — ${filters.yearMin} full-year results.`
                    : activePreset === 'goty-winners'
                      ? 'Games recognized with Game of the Year or major industry awards — score reflects quality and data strength independently.'
                      : activePreset === 'hidden-gems'
                        ? 'Critic-approved games with fewer than 1,500 reviews — high quality, low visibility.'
                        : activePreset === 'all-time-top'
                          ? 'All-time highest-rated games with critic coverage across multiple primary sources.'
                          : activePreset === 'best-deals'
                            ? 'Discounted, high-signal games with tracked store prices.'
                            : activePreset === 'free-games'
                              ? 'Games currently tracked as free through store or FreeToGame data.'
                              : activePreset !== null
                                ? 'Curated from the GameMetrix catalog — sorted by reliability-weighted score.'
                                : activePage === 'suggestions'
                                  ? 'Top-rated games you haven\'t played, liked, or saved yet — find your next play.'
                                  : `Your local ${pageTitle.toLowerCase()} list.`}
                </p>
              </div>
            )}

            {filters.developer || filters.publisher || filters.genre || filters.platform || filters.dealMode !== 'all' ? (
              <div className="active-filter-row" aria-label="Active filters">
                {filters.dealMode !== 'all' ? (
                  <button type="button" onClick={() => { setFilters((current) => ({ ...current, dealMode: 'all' })); setActivePreset(null) }}>
                    Deal: {filters.dealMode === 'best' ? 'Best Deals' : 'Free Games'} ×
                  </button>
                ) : null}
                {filters.developer ? (
                  <button type="button" onClick={() => clearFilter('developer')}>
                    Developer: {filters.developer} ×
                  </button>
                ) : null}
                {filters.publisher ? (
                  <button type="button" onClick={() => clearFilter('publisher')}>
                    Publisher: {filters.publisher} ×
                  </button>
                ) : null}
                {filters.genre ? (
                  <button type="button" onClick={() => clearFilter('genre')}>
                    Genre: {filters.genre} ×
                  </button>
                ) : null}
                {filters.platform ? (
                  <button type="button" onClick={() => clearFilter('platform')}>
                    Platform: {filters.platform} ×
                  </button>
                ) : null}
              </div>
            ) : null}

            {filtersOpen ? (
              <FilterBar
                key={`${pendingApply}-${facets.years.at(-1) ?? 1970}-${facets.years[0] ?? new Date().getFullYear()}`}
                facets={facets}
                filters={filters}
                onChange={setFilters}
                onApply={() => setPendingApply((n) => n + 1)}
              />
            ) : null}

            <div className="list-toolbar">
              <button
                type="button"
                className={`filter-toggle-button${filtersOpen ? ' is-active' : ''}`}
                onClick={() => setFiltersOpen((o) => !o)}
                title={filtersOpen ? 'Hide filters' : 'Show filters'}
              >
                <SlidersHorizontal size={15} aria-hidden="true" />
                <span>Filters</span>
              </button>
              <div className="sort-label">
                <span>Sort By:</span>
                <select
                  aria-label="Sort games"
                  value={filters.sort}
                  onChange={(event) =>
                    setFilters((current) => ({
                      ...current,
                      sort: event.target.value as GameSort,
                    }))
                  }
                >
                  {sortOptions.map((option) => (
                    <option value={option.value} key={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="sort-direction-button"
                  title={filters.direction === 'desc' ? 'High to low' : 'Low to high'}
                  onClick={() =>
                    setFilters((current) => ({
                      ...current,
                      direction: current.direction === 'desc' ? 'asc' : 'desc',
                    }))
                  }
                >
                  {filters.direction === 'desc' ? (
                    <ArrowDown size={15} aria-hidden="true" />
                  ) : (
                    <ArrowUp size={15} aria-hidden="true" />
                  )}
                </button>
                <span className="sort-direction-text">
                  {filters.direction === 'desc' ? 'High to low' : 'Low to high'}
                </span>
              </div>
              <div className="view-toggle" aria-label="View mode">
                <button
                  type="button"
                  className={viewMode === 'list' ? 'is-active' : ''}
                  onClick={() => setViewMode('list')}
                  title="List view"
                >
                  <List size={17} aria-hidden="true" />
                </button>
                <button
                  type="button"
                  className={viewMode === 'grid' ? 'is-active' : ''}
                  onClick={() => setViewMode('grid')}
                  title="Grid view"
                >
                  <Grid2X2 size={16} aria-hidden="true" />
                </button>
              </div>
            </div>

            {error ? <p className="status status-error">{error}</p> : null}
            {isLoading ? (
              <div className={`game-list game-list-${viewMode}`} aria-hidden="true">
                {Array.from({ length: PAGE_SIZE / 3 }, (_, i) => (
                  <div key={i} className="skeleton-card" />
                ))}
              </div>
            ) : null}
            {!isLoading && visibleGames.length === 0 ? (
              activePage === 'catalog' ? (
                <div className="empty-state">
                  <p>No games match these filters.</p>
                  <button type="button" className="apply-button" onClick={goHome}>
                    Reset filters
                  </button>
                </div>
              ) : activePage === 'suggestions' ? (
                <div className="empty-state">
                  <p>Nothing to suggest yet.</p>
                  <p className="empty-hint">
                    Suggestions exclude games you have played, liked, or saved — browse the catalog to get started.
                  </p>
                  <button type="button" className="apply-button" onClick={goHome}>
                    Browse the catalog
                  </button>
                </div>
              ) : (
                <div className="empty-state">
                  <p>No games in {pageTitle} yet.</p>
                  <p className="empty-hint">
                    Add games with the action icons on any game card.
                  </p>
                  <button type="button" className="apply-button" onClick={goHome}>
                    Browse the catalog
                  </button>
                </div>
              )
            ) : null}

            <div className={`game-list game-list-${viewMode}`}>
              {visibleGames.map((game) => (
                <GameCard
                  key={`${game.id}-${game.slug}`}
                  game={game}
                  compact={viewMode === 'grid'}
                  isFavorite={collectionSets.favorites.has(game.slug)}
                  isLiked={collectionSets.liked.has(game.slug)}
                  isPlaying={collectionSets.playing.has(game.slug)}
                  isSeen={collectionSets.seen.has(game.slug)}
                  isCompleted={collectionSets.completed.has(game.slug)}
                  isWatchlisted={collectionSets.watchlist.has(game.slug)}
                  onOpenDetail={saveCatalogSnapshot}
                  onOpenTrailer={handleOpenTrailer}
                  onFilterDeveloper={handleFilterDeveloper}
                  onFilterGenre={handleFilterGenre}
                  onFilterPublisher={handleFilterPublisher}
                  onToggleCollection={handleToggleCollection}
                />
              ))}
            </div>
            <div ref={loaderRef} className="scroll-sentinel" aria-hidden="true">
              {isLoadingMore ? <p className="status">Loading more…</p> : null}
            </div>
          </section>
        )}
      </section>

      <footer className="catalog-attribution">
        Supplementary catalog metadata and imagery may be provided by{' '}
        <a href="https://rawg.io/" target="_blank" rel="noopener noreferrer">RAWG</a>.
        Rating and store sources are named and linked on each game.
      </footer>

      {trailerGame ? (
        <TrailerModal
          title={trailerGame.title}
          videoId={trailerVideoId}
          loading={isTrailerLoading}
          onClose={() => {
            setTrailerGame(null)
            setTrailerVideoId(null)
          }}
        />
      ) : null}
    </main>
  )
}

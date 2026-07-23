/* eslint-disable react-hooks/set-state-in-effect */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Search } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'
import './App.css'
import { AlertsPanel } from './components/AlertsPanel'
import { ActiveFilterChips, type ClearableFilterKey } from './components/ActiveFilterChips'
import { CatalogEmptyState } from './components/CatalogEmptyState'
import { CatalogSettings } from './components/CatalogSettings'
import { CatalogToolbar, type ViewMode } from './components/CatalogToolbar'
import { FilterBar } from './components/FilterBar'
import { GameCard } from './components/GameCard'
import { MobileTabBar } from './components/MobileTabBar'
import { RatingExplainer } from './components/RatingExplainer'
import { SideRail } from './components/SideRail'
import { TrailerModal } from './components/TrailerModal'
import {
  BEST_OF_YEAR_RANGE,
  CURRENT_YEAR,
  DEFAULT_FILTERS,
  PAGE_SIZE,
  ROUTABLE_MAIN_PAGES,
  collectionLabels,
  collectionPageMap,
  describeCatalogPage,
  findPreset,
  formatRoundedThousands,
  readUrlFilters,
  utilityNavItems,
  type ActivePage,
  type CuratedPreset,
  type MainPage,
  type UtilityPage,
} from './catalog/config'
import {
  findGameCardElement,
  readCatalogSnapshot,
  writeCatalogSnapshot,
  type CatalogSnapshot,
} from './catalog/snapshot'
import { useCatalogScroll } from './catalog/useCatalogScroll'
import {
  getFacets,
  getGameTrailer,
  getGames,
  getIntegrationStatus,
} from './services/games'
import type { CollectionKey } from './state/collections'
import { useAccount } from './state/useAccount'
import { useCollectionActions } from './state/useCollectionActions'
import type { Facets, Game, GameFilters, GameSort, ProviderStatus } from './types/game'

export type { UtilityPage }

const SKELETON_CARD_COUNT = PAGE_SIZE / 3
const SCROLL_SENTINEL_ROOT_MARGIN = '300px'
const DEFAULT_PROVIDER_COUNT = 5
// Frames/timers the restore re-applies the scroll position on, so late layout
// shifts (fonts, images) cannot leave the page a few pixels off.
const RESTORE_SETTLE_DELAY_MS = 80

const useIsomorphicLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect

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
  const { account } = useAccount()
  const [providerStatuses, setProviderStatuses] = useState<ProviderStatus[]>([])
  const [catalogTotal, setCatalogTotal] = useState(initialTotal)
  const [libraryTotal, setLibraryTotal] = useState(initialTotal)
  const [isLoading, setIsLoading] = useState(hasUrlFilters || initialGames.length === 0)
  const [trailerGame, setTrailerGame] = useState<Game | null>(null)
  const [trailerVideoId, setTrailerVideoId] = useState<string | null>(null)
  const [isTrailerLoading, setIsTrailerLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<ViewMode>('list')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [activePreset, setActivePreset] = useState<string | null>(null)
  const [mobileMoreOpen, setMobileMoreOpen] = useState(false)
  const [fetchKey, setFetchKey] = useState(0)
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(!hasUrlFilters && initialGames.length < initialTotal)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const loaderRef = useRef<HTMLDivElement>(null)
  const latestCatalogRef = useRef<CatalogSnapshot | null>(null)
  const snapshotAnchorRef = useRef<{ slug: string; viewportTop: number } | null>(null)
  const {
    mastheadVisible,
    mastheadVisibleRef,
    lastScrollYRef,
    mastheadRef,
    setMastheadVisibility,
    scrollToTop,
  } = useCatalogScroll()
  // Holds the `${fetchKey}:${offset}` pair the games list currently reflects;
  // pre-seeded on snapshot restore so the mount run keeps the restored list.
  const lastFetchSignatureRef = useRef<string | null>(
    initialGames.length && !hasUrlFilters ? '0:0' : null,
  )
  // True from the moment a snapshot restore starts until its state has fully
  // committed. The restore re-applies offset/filters/games via setState in a
  // layout effect, which spans two renders; the mount runs of the fetch and
  // filter-reset effects still see the initial offset=0 / default filters and
  // would otherwise clear the restored list and refetch page 0. This flag makes
  // both effects no-ops (they only keep their signature refs in sync) until the
  // restore settles.
  const restoreInProgressRef = useRef(false)
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

    restoreInProgressRef.current = true
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
    setMastheadVisibility(snapshot.mastheadVisible)
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
  }, [lastScrollYRef, mastheadVisibleRef])

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
  }, [lastScrollYRef, mastheadVisibleRef])

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
    const settleTimer = window.setTimeout(restorePosition, RESTORE_SETTLE_DELAY_MS)

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
    // During a snapshot restore the filters transition default → restored, which
    // is not a user-driven filter change and must not reset the loaded pages.
    if (restoreInProgressRef.current) {
      lastFilterResetSignatureRef.current = filterResetSignature
      return
    }
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
    // While a snapshot is being restored the games list is already authoritative;
    // every run here belongs to the two-render restore cascade (offset 0 → restored
    // offset), so keep the signature ref in sync but never clear or refetch.
    if (restoreInProgressRef.current) {
      lastFetchSignatureRef.current = `${fetchKey}:${offset}`
      return
    }
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

  // Restore is complete once its state has committed (restoredSnapshot is set in
  // the same batched update as the offset/filters/games). Defined AFTER the
  // fetch and filter-reset effects so that, in the settling commit, those two
  // still observe the flag as set and skip before it is finally cleared here.
  useEffect(() => {
    if (restoredSnapshot) restoreInProgressRef.current = false
  }, [restoredSnapshot])

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
      { rootMargin: SCROLL_SENTINEL_ROOT_MARGIN },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [catalogTotal, hasMore, isLoadingMore, isLoading])

  const { collections, collectionSets, toggle: handleToggleCollection } = useCollectionActions(setError)

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

  const goHome = () => {
    if (location.pathname !== '/' || location.search) navigate('/')
    snapshotAnchorRef.current = null
    scrollToTop()
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

  const clearFilter = (key: ClearableFilterKey) => {
    setFilters((current) => ({ ...current, [key]: '' }))
  }

  const clearDealMode = () => {
    setFilters((current) => ({ ...current, dealMode: 'all' }))
    setActivePreset(null)
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

  const openAccount = () => navigate(account ? '/account' : '/login')

  const isUtilityPage = utilityNavItems.some((item) => item.id === activePage)
  const isCuratedView = activePage !== 'catalog' || activePreset !== null
  const headingTitle = activePreset !== null && activePreset !== 'best-of-year'
    ? (findPreset(activePreset)?.label ?? pageTitle)
    : pageTitle

  return (
    <main className="app-shell">
      <SideRail
        activePage={activePage}
        activePreset={activePreset}
        collections={collections}
        isSignedIn={Boolean(account)}
        onOpenAccount={openAccount}
        onOpenMainPage={openMainPage}
        onOpenPreset={openPreset}
        onOpenUtilityPage={openUtilityPage}
      />

      <MobileTabBar
        activePage={activePage}
        activePreset={activePreset}
        isSignedIn={Boolean(account)}
        moreOpen={mobileMoreOpen}
        onOpenAccount={openAccount}
        onOpenMainPage={openMainPage}
        onOpenUtilityPage={openUtilityPage}
        onToggleMore={() => setMobileMoreOpen((open) => !open)}
      />

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
              onFocus={() => setMastheadVisibility(true)}
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
          <span>{readyProviders} / {providerStatuses.length || DEFAULT_PROVIDER_COUNT} providers ready</span>
        </div>

        {isUtilityPage ? (
          <section className="utility-panel">
            <h1>{pageTitle}</h1>
            {activePage === 'settings' ? (
              <CatalogSettings
                filtersOpen={filtersOpen}
                viewMode={viewMode}
                onChangeFiltersOpen={setFiltersOpen}
                onChangeViewMode={setViewMode}
              />
            ) : activePage === 'alerts' ? (
              <AlertsPanel watchlistSlugs={collections.watchlist} />
            ) : activePage === 'about' ? (
              <RatingExplainer />
            ) : null}
          </section>
        ) : (
          <section className="catalog" id="catalog">
            {isCuratedView ? (
              <div className="page-heading">
                <h1>{headingTitle}</h1>
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
                <p>{describeCatalogPage(activePreset, activePage, filters.yearMin, pageTitle)}</p>
              </div>
            ) : (
              <div className="page-heading page-heading-catalog">
                <h1>Game rankings</h1>
                <p>Four-source ratings with current compatibility, playtime and price context.</p>
              </div>
            )}

            <ActiveFilterChips
              filters={filters}
              onClearDealMode={clearDealMode}
              onClearFilter={clearFilter}
            />

            {filtersOpen ? (
              <FilterBar
                key={`${pendingApply}-${facets.years.at(-1) ?? 1970}-${facets.years[0] ?? CURRENT_YEAR}`}
                facets={facets}
                filters={filters}
                onChange={setFilters}
                onApply={() => setPendingApply((n) => n + 1)}
              />
            ) : null}

            <CatalogToolbar
              direction={filters.direction}
              filtersOpen={filtersOpen}
              sort={filters.sort}
              viewMode={viewMode}
              onChangeSort={(sort: GameSort) => setFilters((current) => ({ ...current, sort }))}
              onChangeViewMode={setViewMode}
              onToggleDirection={() =>
                setFilters((current) => ({
                  ...current,
                  direction: current.direction === 'desc' ? 'asc' : 'desc',
                }))
              }
              onToggleFilters={() => setFiltersOpen((o) => !o)}
            />

            {error ? <p className="status status-error">{error}</p> : null}
            {isLoading ? (
              <div className={`game-list game-list-${viewMode}`} aria-hidden="true">
                {Array.from({ length: SKELETON_CARD_COUNT }, (_, i) => (
                  <div key={i} className="skeleton-card" />
                ))}
              </div>
            ) : null}
            {!isLoading && visibleGames.length === 0 ? (
              <CatalogEmptyState
                activePage={activePage}
                pageTitle={pageTitle}
                onBrowseCatalog={goHome}
              />
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

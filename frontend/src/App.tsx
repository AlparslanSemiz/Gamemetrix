import {
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react'
import { useLocation, useNavigate } from 'react-router'
import './App.css'
import { CatalogWorkspace } from './components/catalog-workspace'
import type { ViewMode } from './components/CatalogToolbar'
import { MobileTabBar } from './components/MobileTabBar'
import { SideRail } from './components/SideRail'
import { TrailerModal } from './components/TrailerModal'
import {
  CURRENT_YEAR,
  DEFAULT_FILTERS,
  ROUTABLE_MAIN_PAGES,
  readUrlFilters,
  type ActivePage,
  type MainPage,
  type UtilityPage,
} from './catalog/config'
import { useDebouncedValue } from './hooks/useDebouncedValue'
import {
  mergeFiltersIntoSearch,
  sameFilterSearch,
} from './catalog/queryParams'
import { catalogPageTitle, visibleCatalogGames } from './catalog/presentation'
import {
  useCatalogActions,
  useCatalogFilterActions,
} from './catalog/useCatalogActions'
import { FACETS_ERROR, useCatalogBootstrap } from './catalog/useCatalogBootstrap'
import { useCollectionGames } from './catalog/useCollectionGames'
import { useCatalogScroll } from './catalog/useCatalogScroll'
import {
  useCatalogBackgroundRefresh,
  useCatalogSnapshot,
} from './catalog/useCatalogSnapshot'
import {
  useCatalogInfiniteScroll,
  useCatalogLoadEffects,
  useCatalogPaginationState,
} from './catalog/useCatalogPagination'
import { useTrailer } from './catalog/useTrailer'
import { useAccount } from './state/useAccount'
import { useCollectionActions } from './state/useCollectionActions'
import type { CatalogGame, Facets, GameFilters } from './types/game'
import type { CatalogSnapshot } from './catalog/snapshot'
import type { RankingGenre } from './server-api.server'

export type { UtilityPage }

// One rich card keeps fresh SSR within the LCP budget; the complete 24-row
// loader payload remains in structured data and paints immediately on hydration.
// Snapshot-based client returns bypass this cap and render every saved card.
const SSR_CATALOG_CARD_COUNT = 1
const SEARCH_DEBOUNCE_MS = 250
const subscribeToHydration = () => () => undefined

interface AppContentProps {
  initialGames?: CatalogGame[]
  initialTotal?: number
  initialPage?: UtilityPage
  initialSnapshot?: CatalogSnapshot | null
  footerGenres?: RankingGenre[]
}

export function AppContent({
  initialGames = [],
  initialTotal = 0,
  initialPage,
  initialSnapshot = null,
  footerGenres = [],
}: AppContentProps) {
  const location = useLocation()
  const navigate = useNavigate()
  const lastLocationKeyRef = useRef(location.key)
  // Last query string this component wrote itself, and one it adopted from a
  // back/forward move whose filter state has not caught up yet.
  const writtenSearchRef = useRef<string | null>(null)
  const adoptedSearchRef = useRef<string | null>(null)
  // Query string a catalog action is navigating to; the URL writer stands aside
  // until it arrives so it cannot `replace` the entry the action is about to push.
  const pendingSearchRef = useRef<string | null>(null)
  const hydrated = useSyncExternalStore(
    subscribeToHydration,
    () => true,
    () => false,
  )
  const catalogEnabled = initialPage === undefined
  const requestedView = new URLSearchParams(location.search).get('view') as MainPage | null
  const routeInitialPage: ActivePage = initialPage
    ?? (requestedView && ROUTABLE_MAIN_PAGES.has(requestedView) ? requestedView : 'catalog')
  // Seeded once at mount: a deep link like /?developer=Larian arrives from a
  // detail-page link and must apply its filter instead of the curated home list.
  const urlFilters = readUrlFilters(location.search)
  const hasUrlFilters = Object.keys(urlFilters).length > 0
  // A saved snapshot is reused when the URL carries no filters, or exactly the
  // snapshot's filters (the address bar mirrors them, so a back-navigation lands
  // on `/?q=…` for the very list that was saved).
  const snapshotMatchesUrl = initialSnapshot !== null && (
    !hasUrlFilters
    || sameFilterSearch(location.search, mergeFiltersIntoSearch('', initialSnapshot.filters))
  )
  const restoredSnapshot = catalogEnabled && snapshotMatchesUrl ? initialSnapshot : null
  const seededGames = restoredSnapshot?.games ?? initialGames
  const [activePage, setActivePage] = useState<ActivePage>(
    restoredSnapshot?.activePage ?? routeInitialPage,
  )
  const deferredActivePage = useDeferredValue(activePage)
  const [games, setGames] = useState<CatalogGame[]>(seededGames)
  const [facets, setFacets] = useState<Facets>({ genres: [], years: [], platforms: [], developers: [] })
  const [filters, setFilters] = useState<GameFilters>(() => (
    restoredSnapshot?.filters ?? { ...DEFAULT_FILTERS, ...urlFilters }
  ))
  const [pendingApply, setPendingApply] = useState(0)
  // Typing updates `filters.q` at once (the box stays responsive) but the catalog
  // is only queried — and the address bar only written — once typing pauses.
  const debouncedQuery = useDebouncedValue(filters.q, SEARCH_DEBOUNCE_MS, (next) => next.trim() === '')
  const searchedFilters = useMemo(
    () => (debouncedQuery === filters.q ? filters : { ...filters, q: debouncedQuery }),
    [debouncedQuery, filters],
  )
  const pagination = useCatalogPaginationState({
    filters: searchedFilters,
    initialGames: seededGames,
    initialHasMore: restoredSnapshot?.hasMore,
    initialOffset: restoredSnapshot?.offset,
    initialTotal: restoredSnapshot?.catalogTotal ?? initialTotal,
    pendingApply,
  })
  const {
    isLoadingMore,
    loadMoreError,
    loaderRef,
    retryLoadMore,
  } = pagination
  const { account } = useAccount()
  const [catalogTotal, setCatalogTotal] = useState(
    restoredSnapshot?.catalogTotal ?? initialTotal,
  )
  const [libraryTotal, setLibraryTotal] = useState(
    restoredSnapshot?.libraryTotal ?? initialTotal,
  )
  const [isLoading, setIsLoading] = useState(catalogEnabled && seededGames.length === 0)
  const [error, setError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<ViewMode>(restoredSnapshot?.viewMode ?? 'list')
  const [filtersOpen, setFiltersOpen] = useState(restoredSnapshot?.filtersOpen ?? false)
  const [activePreset, setActivePreset] = useState<string | null>(
    restoredSnapshot?.activePreset ?? null,
  )
  useEffect(() => {
    if (lastLocationKeyRef.current === location.key) return
    lastLocationKeyRef.current = location.key
    pendingSearchRef.current = null
    if (location.pathname !== '/') return
    // Our own filter write: state already matches, nothing else to reset.
    if (location.search === writtenSearchRef.current) return
    if (routeInitialPage === 'catalog' && !sameFilterSearch(location.search, mergeFiltersIntoSearch('', searchedFilters))) {
      // Back/forward (or a pasted link) to a different filter set.
      adoptedSearchRef.current = location.search
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setFilters({ ...DEFAULT_FILTERS, ...readUrlFilters(location.search) })
      setPendingApply((count) => count + 1)
    }
    // The navigation actions already update state. This also covers browser
    // back/forward, where only the URL changes because `shouldRevalidate`
    // deliberately keeps the route loader dormant.
    setActivePage(routeInitialPage)
    setActivePreset(null)
  }, [location.key, location.pathname, location.search, routeInitialPage, searchedFilters])

  useEffect(() => {
    if (!catalogEnabled || activePage !== 'catalog' || location.pathname !== '/') return
    const wanted = mergeFiltersIntoSearch(location.search, searchedFilters)
    if (pendingSearchRef.current !== null) return
    if (adoptedSearchRef.current !== null) {
      // A back/forward move is still loading its filters into state; writing now
      // would overwrite the entry the visitor navigated to.
      if (!sameFilterSearch(location.search, wanted)) return
      adoptedSearchRef.current = null
    }
    if (wanted === location.search) return
    writtenSearchRef.current = wanted
    void navigate({ search: wanted }, { replace: true, preventScrollReset: true })
  }, [activePage, catalogEnabled, location.pathname, location.search, navigate, searchedFilters])
  const [mobileMoreOpen, setMobileMoreOpen] = useState(false)
  const catalogScroll = useCatalogScroll(restoredSnapshot)
  const {
    mastheadVisible,
    mastheadRef,
    setMastheadVisibility,
    scrollToTop,
  } = catalogScroll
  const {
    filtersRef,
    restoreInProgressRef,
    saveCatalogSnapshot,
    snapshotAnchorRef,
  } = useCatalogSnapshot({
    enabled: catalogEnabled,
    initialSnapshot: restoredSnapshot,
    pagination,
    scroll: catalogScroll,
    values: {
      activePage,
      activePreset,
      catalogTotal,
      filters: searchedFilters,
      filtersOpen,
      games,
      libraryTotal,
      viewMode,
    },
  })

  const { retry: retryBootstrap } = useCatalogBootstrap({
    enabled: catalogEnabled,
    setError,
    setFacets,
    setLibraryTotal,
  })

  useCatalogLoadEffects({
    catalogTotal,
    enabled: catalogEnabled,
    filters: searchedFilters,
    filtersRef,
    pagination,
    pendingApply,
    restoreInProgressRef,
    setCatalogTotal,
    setError,
    setGames,
    setIsLoading,
  })

  useCatalogBackgroundRefresh({
    enabled: catalogEnabled,
    snapshot: restoredSnapshot,
    setCatalogTotal,
    setGames,
  })

  const { collections, collectionSets, toggle: handleToggleCollection } = useCollectionActions(setError)
  const savedList = useCollectionGames(activePage, collections, games)

  useCatalogInfiniteScroll({
    catalogTotal,
    enabled: (
      catalogEnabled
      && savedList.collectionKey === undefined
      && deferredActivePage === activePage
    ),
    isLoading,
    pagination,
  })

  const visibleGames = useMemo(
    () => savedList.collectionKey
      ? savedList.games
      : visibleCatalogGames(activePage, collections, games),
    [activePage, collections, games, savedList.collectionKey, savedList.games],
  )
  const renderedGames = (
    (!hydrated && !restoredSnapshot)
    || deferredActivePage !== activePage
  )
    ? visibleGames.slice(0, SSR_CATALOG_CARD_COUNT)
    : visibleGames
  // Cards held back from the first render are replaced by same-size placeholders
  // so the footer below does not jump when hydration fills the list in.
  const deferredCardCount = visibleGames.length - renderedGames.length
  const pageTitle = useMemo(
    () => catalogPageTitle(activePage, activePreset, searchedFilters),
    [activePage, activePreset, searchedFilters],
  )

  const trailer = useTrailer()
  const actions = useCatalogActions({
    accountIsActive: Boolean(account),
    saveCatalogSnapshot,
    scrollToTop,
    setActivePage,
    setActivePreset,
    setFilters,
    setMobileMoreOpen,
    pendingSearchRef,
    setPendingApply,
    snapshotAnchorRef,
  })
  const filterActions = useCatalogFilterActions(setActivePage, setFilters)

  return (
    <div className="app-shell">
      <SideRail
        activePage={activePage}
        activePreset={activePreset}
        collections={collections}
        isSignedIn={Boolean(account)}
        onOpenAccount={actions.openAccount}
        onOpenMainPage={actions.openMainPage}
        onOpenPreset={actions.openPreset}
        onOpenUtilityPage={actions.openUtilityPage}
      />

      <MobileTabBar
        activePage={activePage}
        activePreset={activePreset}
        isSignedIn={Boolean(account)}
        moreOpen={mobileMoreOpen}
        onOpenAccount={actions.openAccount}
        onOpenMainPage={actions.openMainPage}
        onOpenUtilityPage={actions.openUtilityPage}
        onToggleMore={() => setMobileMoreOpen((open) => !open)}
      />

      <CatalogWorkspace
        activePage={activePage}
        activePreset={activePreset}
        catalogTotal={catalogTotal}
        collections={collections}
        collectionSets={collectionSets}
        deferredCardCount={deferredCardCount}
        error={savedList.error ?? error}
        onRetryError={!savedList.error && error === FACETS_ERROR ? retryBootstrap : undefined}
        facets={facets}
        filters={filters}
        filtersOpen={filtersOpen}
        games={games}
        isLoading={isLoading || savedList.isLoading}
        isLoadingMore={isLoadingMore}
        libraryTotal={libraryTotal}
        loadMoreError={loadMoreError}
        loaderRef={loaderRef}
        mastheadRef={mastheadRef}
        mastheadVisible={mastheadVisible}
        pageTitle={pageTitle}
        pendingApply={pendingApply}
        viewMode={viewMode}
        visibleGames={renderedGames}
        onApplyFilters={() => setPendingApply((count) => count + 1)}
        onBrowseCatalog={actions.goHome}
        onChangeFilters={setFilters}
        onChangeFiltersOpen={setFiltersOpen}
        onChangeViewMode={setViewMode}
        onClearDealMode={actions.clearDealMode}
        onClearFilter={actions.clearFilter}
        onFilterDeveloper={filterActions.filterDeveloper}
        onFilterGenre={filterActions.filterGenre}
        onFilterPublisher={filterActions.filterPublisher}
        onFocusSearch={() => setMastheadVisibility(true)}
        onOpenDetail={saveCatalogSnapshot}
        onOpenTrailer={trailer.open}
        onRetryLoadMore={retryLoadMore}
        onToggleCollection={handleToggleCollection}
      />

      <footer className="catalog-attribution">
        <nav className="catalog-footer-nav" aria-label="GameMetrix information">
          <a href="/about">Scoring methodology</a>
          <a href="/best/linux-games">Best Linux games</a>
          <a href="/best/steam-deck-games">Runs well on Linux / Deck</a>
          <a href="/deals">PC game deals</a>
          <a href={`/best/games/${CURRENT_YEAR}`}>Best of {CURRENT_YEAR}</a>
          <a href={`/best/games/${CURRENT_YEAR - 1}`}>Best of {CURRENT_YEAR - 1}</a>
          {footerGenres.map((genre) => (
            <a key={genre.slug} href={`/best/${genre.slug}-games`}>{genre.name}</a>
          ))}
          <a href="/impressum">Impressum</a>
          <a href="/privacy">Privacy</a>
        </nav>
        <span>
          Supplementary catalog metadata and imagery may be provided by{' '}
          <a href="https://rawg.io/" target="_blank" rel="noopener noreferrer">RAWG</a>
          {' '}and{' '}
          <a href="https://gamebrain.co/" target="_blank" rel="noopener noreferrer">GameBrain</a>.
          Rating and store sources are named and linked on each game.
        </span>
      </footer>

      {trailer.game ? (
        <TrailerModal
          title={trailer.game.title}
          videoId={trailer.videoId}
          loading={trailer.isLoading}
          onClose={trailer.close}
        />
      ) : null}
    </div>
  )
}

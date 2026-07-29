import {
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react'
import { useLocation } from 'react-router'
import './App.css'
import { CatalogWorkspace } from './components/catalog-workspace'
import type { ViewMode } from './components/CatalogToolbar'
import { MobileTabBar } from './components/MobileTabBar'
import { SideRail } from './components/SideRail'
import { TrailerModal } from './components/TrailerModal'
import {
  DEFAULT_FILTERS,
  ROUTABLE_MAIN_PAGES,
  readUrlFilters,
  type ActivePage,
  type MainPage,
  type UtilityPage,
} from './catalog/config'
import { catalogPageTitle, visibleCatalogGames } from './catalog/presentation'
import {
  useCatalogActions,
  useCatalogFilterActions,
} from './catalog/useCatalogActions'
import { useCatalogBootstrap } from './catalog/useCatalogBootstrap'
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
import type { CatalogGame, Facets, GameFilters, ProviderStatus } from './types/game'
import type { CatalogSnapshot } from './catalog/snapshot'

export type { UtilityPage }

// One rich card keeps fresh SSR within the LCP budget; the complete 24-row
// loader payload remains in structured data and paints immediately on hydration.
// Snapshot-based client returns bypass this cap and render every saved card.
const SSR_CATALOG_CARD_COUNT = 1
const subscribeToHydration = () => () => undefined

interface AppContentProps {
  initialGames?: CatalogGame[]
  initialTotal?: number
  initialPage?: UtilityPage
  initialSnapshot?: CatalogSnapshot | null
}

export function AppContent({
  initialGames = [],
  initialTotal = 0,
  initialPage,
  initialSnapshot = null,
}: AppContentProps) {
  const location = useLocation()
  const lastLocationKeyRef = useRef(location.key)
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
  const restoredSnapshot = catalogEnabled && !hasUrlFilters ? initialSnapshot : null
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
  const pagination = useCatalogPaginationState({
    filters,
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
  const [providerStatuses, setProviderStatuses] = useState<ProviderStatus[]>([])
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
    if (location.pathname !== '/') return
    // The navigation actions already update state. This also covers browser
    // back/forward, where only the URL changes because `shouldRevalidate`
    // deliberately keeps the route loader dormant.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setActivePage(routeInitialPage)
    setActivePreset(null)
  }, [location.key, location.pathname, routeInitialPage])
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
      filters,
      filtersOpen,
      games,
      libraryTotal,
      viewMode,
    },
  })

  useCatalogBootstrap({
    enabled: catalogEnabled,
    setError,
    setFacets,
    setLibraryTotal,
    setProviderStatuses,
  })

  useCatalogLoadEffects({
    catalogTotal,
    enabled: catalogEnabled,
    filters,
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
  const pageTitle = useMemo(
    () => catalogPageTitle(activePage, activePreset, filters),
    [activePage, activePreset, filters],
  )

  const readyProviders = providerStatuses.filter((p) => p.status === 'ready').length
  const trailer = useTrailer()
  const actions = useCatalogActions({
    accountIsActive: Boolean(account),
    saveCatalogSnapshot,
    scrollToTop,
    setActivePage,
    setActivePreset,
    setFilters,
    setMobileMoreOpen,
    setPendingApply,
    snapshotAnchorRef,
  })
  const filterActions = useCatalogFilterActions(setActivePage, setFilters)

  return (
    <main className="app-shell">
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
        error={savedList.error ?? error}
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
        providerCount={providerStatuses.length}
        readyProviders={readyProviders}
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
          <a href="/best/steam-deck-games">Steam Deck games</a>
          <a href="/deals">PC game deals</a>
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
    </main>
  )
}

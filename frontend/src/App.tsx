import { useMemo, useState } from 'react'
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
  useCatalogRestoreCompletion,
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
import type { Facets, Game, GameFilters, ProviderStatus } from './types/game'

export type { UtilityPage }

interface AppContentProps {
  initialGames?: Game[]
  initialTotal?: number
  initialPage?: UtilityPage
}

export function AppContent({ initialGames = [], initialTotal = 0, initialPage }: AppContentProps) {
  const location = useLocation()
  const requestedView = new URLSearchParams(location.search).get('view') as MainPage | null
  const routeInitialPage: ActivePage = initialPage
    ?? (requestedView && ROUTABLE_MAIN_PAGES.has(requestedView) ? requestedView : 'catalog')
  // Seeded once at mount: a deep link like /?developer=Larian arrives from a
  // detail-page link and must apply its filter instead of the curated home list.
  const urlFilters = readUrlFilters(location.search)
  const hasUrlFilters = Object.keys(urlFilters).length > 0
  const [activePage, setActivePage] = useState<ActivePage>(routeInitialPage)
  const [games, setGames] = useState<Game[]>(hasUrlFilters ? [] : initialGames)
  const [facets, setFacets] = useState<Facets>({ genres: [], years: [], platforms: [], developers: [] })
  const [filters, setFilters] = useState<GameFilters>(() => ({ ...DEFAULT_FILTERS, ...urlFilters }))
  const [pendingApply, setPendingApply] = useState(0)
  const pagination = useCatalogPaginationState({
    filters,
    hasUrlFilters,
    initialGames,
    initialTotal,
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
  const [catalogTotal, setCatalogTotal] = useState(initialTotal)
  const [libraryTotal, setLibraryTotal] = useState(initialTotal)
  const [isLoading, setIsLoading] = useState(hasUrlFilters || initialGames.length === 0)
  const [error, setError] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<ViewMode>('list')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [activePreset, setActivePreset] = useState<string | null>(null)
  const [mobileMoreOpen, setMobileMoreOpen] = useState(false)
  const catalogScroll = useCatalogScroll()
  const {
    mastheadVisible,
    mastheadRef,
    setMastheadVisibility,
    scrollToTop,
  } = catalogScroll
  const {
    filtersRef,
    restoredSnapshot,
    restoreInProgressRef,
    saveCatalogSnapshot,
    snapshotAnchorRef,
  } = useCatalogSnapshot({
    hasUrlFilters,
    pagination,
    pendingApply,
    routeInitialPage,
    scroll: catalogScroll,
    setters: {
      setActivePage,
      setActivePreset,
      setCatalogTotal,
      setFilters,
      setFiltersOpen,
      setGames,
      setIsLoading,
      setLibraryTotal,
      setViewMode,
    },
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
    setError,
    setFacets,
    setLibraryTotal,
    setProviderStatuses,
  })

  useCatalogLoadEffects({
    catalogTotal,
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

  useCatalogRestoreCompletion(restoredSnapshot, restoreInProgressRef)

  const { collections, collectionSets, toggle: handleToggleCollection } = useCollectionActions(setError)
  const savedList = useCollectionGames(activePage, collections, games)

  useCatalogInfiniteScroll({
    catalogTotal,
    enabled: savedList.collectionKey === undefined,
    isLoading,
    pagination,
  })

  const visibleGames = useMemo(
    () => savedList.collectionKey
      ? savedList.games
      : visibleCatalogGames(activePage, collections, games),
    [activePage, collections, games, savedList.collectionKey, savedList.games],
  )
  const pageTitle = useMemo(
    () => catalogPageTitle(activePage, activePreset, filters),
    [activePage, activePreset, filters],
  )

  const readyProviders = providerStatuses.filter((p) => p.status === 'ready').length
  const trailer = useTrailer()
  const actions = useCatalogActions({
    accountIsActive: Boolean(account),
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
        visibleGames={visibleGames}
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

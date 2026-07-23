import { Search } from 'lucide-react'
import type {
  Dispatch,
  RefObject,
  SetStateAction,
} from 'react'
import {
  BEST_OF_YEAR_RANGE,
  CURRENT_YEAR,
  PAGE_SIZE,
  describeCatalogPage,
  findPreset,
  formatRoundedThousands,
  utilityNavItems,
  type ActivePage,
} from '../catalog/config'
import type { CollectionKey, Collections } from '../state/collections'
import type { CollectionSets } from '../state/useCollectionActions'
import type {
  Facets,
  Game,
  GameFilters,
  GameSort,
} from '../types/game'
import { ActiveFilterChips, type ClearableFilterKey } from './ActiveFilterChips'
import { AlertsPanel } from './AlertsPanel'
import { CatalogEmptyState } from './CatalogEmptyState'
import { CatalogSettings } from './CatalogSettings'
import { CatalogToolbar, type ViewMode } from './CatalogToolbar'
import { FilterBar } from './FilterBar'
import { GameCard } from './GameCard'
import { RatingExplainer } from './RatingExplainer'

const DEFAULT_PROVIDER_COUNT = 5
const SKELETON_CARD_COUNT = PAGE_SIZE / 3

export interface CatalogWorkspaceProps {
  activePage: ActivePage
  activePreset: string | null
  catalogTotal: number
  collections: Collections
  collectionSets: CollectionSets
  error: string | null
  facets: Facets
  filters: GameFilters
  filtersOpen: boolean
  games: Game[]
  isLoading: boolean
  isLoadingMore: boolean
  libraryTotal: number
  loaderRef: RefObject<HTMLDivElement | null>
  mastheadRef: RefObject<HTMLElement | null>
  mastheadVisible: boolean
  pageTitle: string
  pendingApply: number
  providerCount: number
  readyProviders: number
  viewMode: ViewMode
  visibleGames: Game[]
  onApplyFilters: () => void
  onBrowseCatalog: () => void
  onChangeFilters: Dispatch<SetStateAction<GameFilters>>
  onChangeFiltersOpen: Dispatch<SetStateAction<boolean>>
  onChangeViewMode: Dispatch<SetStateAction<ViewMode>>
  onClearDealMode: () => void
  onClearFilter: (key: ClearableFilterKey) => void
  onFilterDeveloper: (developer: string) => void
  onFilterGenre: (genre: string) => void
  onFilterPublisher: (publisher: string) => void
  onFocusSearch: () => void
  onOpenDetail: (game: Game) => void
  onOpenTrailer: (game: Game) => void
  onToggleCollection: (collection: CollectionKey, slug: string) => void
}

export function CatalogWorkspace(props: CatalogWorkspaceProps) {
  const isUtilityPage = utilityNavItems.some((item) => item.id === props.activePage)
  const isCuratedView = props.activePage !== 'catalog' || props.activePreset !== null
  const headingTitle = props.activePreset && props.activePreset !== 'best-of-year'
    ? (findPreset(props.activePreset)?.label ?? props.pageTitle)
    : props.pageTitle

  return (
    <section
      className={
        `workspace ${
          props.mastheadVisible ? 'masthead-open' : 'masthead-collapsed'
        }`
      }
    >
      <CatalogMasthead
        catalogTotal={props.catalogTotal}
        filters={props.filters}
        libraryTotal={props.libraryTotal}
        mastheadRef={props.mastheadRef}
        visible={props.mastheadVisible}
        onBrowseCatalog={props.onBrowseCatalog}
        onChangeFilters={props.onChangeFilters}
        onFocusSearch={props.onFocusSearch}
      />
      <div className="provider-strip">
        <span>{props.visibleGames.length} shown</span>
        <span>{props.games.length} / {props.catalogTotal || props.games.length} loaded</span>
        <span>
          {props.readyProviders} / {props.providerCount || DEFAULT_PROVIDER_COUNT} providers ready
        </span>
      </div>

      {isUtilityPage ? (
        <UtilityPanel
          activePage={props.activePage}
          collections={props.collections}
          filtersOpen={props.filtersOpen}
          pageTitle={props.pageTitle}
          viewMode={props.viewMode}
          onChangeFiltersOpen={props.onChangeFiltersOpen}
          onChangeViewMode={props.onChangeViewMode}
        />
      ) : (
        <CatalogBody
          {...props}
          headingTitle={headingTitle}
          isCuratedView={isCuratedView}
        />
      )}
    </section>
  )
}

function CatalogBody({
  headingTitle,
  isCuratedView,
  ...props
}: CatalogWorkspaceProps & {
  headingTitle: string
  isCuratedView: boolean
}) {
  return (
    <section className="catalog" id="catalog">
      <CatalogHeading
        activePage={props.activePage}
        activePreset={props.activePreset}
        filters={props.filters}
        headingTitle={headingTitle}
        isCuratedView={isCuratedView}
        pageTitle={props.pageTitle}
        onChangeFilters={props.onChangeFilters}
        onApplyFilters={props.onApplyFilters}
      />
      <ActiveFilterChips
        filters={props.filters}
        onClearDealMode={props.onClearDealMode}
        onClearFilter={props.onClearFilter}
      />
      {props.filtersOpen ? (
        <FilterBar
          key={`${props.pendingApply}-${props.facets.years.at(-1) ?? 1970}-${props.facets.years[0] ?? CURRENT_YEAR}`}
          facets={props.facets}
          filters={props.filters}
          onChange={props.onChangeFilters}
          onApply={props.onApplyFilters}
        />
      ) : null}
      <CatalogToolbar
        direction={props.filters.direction}
        filtersOpen={props.filtersOpen}
        sort={props.filters.sort}
        viewMode={props.viewMode}
        onChangeSort={(sort: GameSort) => {
          props.onChangeFilters((current) => ({ ...current, sort }))
        }}
        onChangeViewMode={props.onChangeViewMode}
        onToggleDirection={() => {
          props.onChangeFilters((current) => ({
            ...current,
            direction: current.direction === 'desc' ? 'asc' : 'desc',
          }))
        }}
        onToggleFilters={() => props.onChangeFiltersOpen((open) => !open)}
      />
      <GameResults
        activePage={props.activePage}
        collectionSets={props.collectionSets}
        error={props.error}
        isLoading={props.isLoading}
        isLoadingMore={props.isLoadingMore}
        loaderRef={props.loaderRef}
        pageTitle={props.pageTitle}
        viewMode={props.viewMode}
        visibleGames={props.visibleGames}
        onBrowseCatalog={props.onBrowseCatalog}
        onFilterDeveloper={props.onFilterDeveloper}
        onFilterGenre={props.onFilterGenre}
        onFilterPublisher={props.onFilterPublisher}
        onOpenDetail={props.onOpenDetail}
        onOpenTrailer={props.onOpenTrailer}
        onToggleCollection={props.onToggleCollection}
      />
    </section>
  )
}

function CatalogMasthead({
  catalogTotal,
  filters,
  libraryTotal,
  mastheadRef,
  visible,
  onBrowseCatalog,
  onChangeFilters,
  onFocusSearch,
}: Pick<
  CatalogWorkspaceProps,
  | 'catalogTotal'
  | 'filters'
  | 'libraryTotal'
  | 'mastheadRef'
  | 'onBrowseCatalog'
  | 'onChangeFilters'
  | 'onFocusSearch'
> & { visible: boolean }) {
  return (
    <header
      ref={mastheadRef}
      className={`masthead ${visible ? 'is-visible' : 'is-hidden'}`}
    >
      <button type="button" className="brand" onClick={onBrowseCatalog}>
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
          onFocus={onFocusSearch}
          onChange={(event) => {
            onChangeFilters((current) => ({
              ...current,
              q: event.target.value,
            }))
          }}
          aria-label="Search games by title"
        />
        <div className="masthead-search-meta">
          <span>
            {formatRoundedThousands(libraryTotal || catalogTotal)} games
          </span>
          <Search size={18} aria-hidden="true" />
        </div>
      </div>
    </header>
  )
}

function UtilityPanel({
  activePage,
  collections,
  filtersOpen,
  pageTitle,
  viewMode,
  onChangeFiltersOpen,
  onChangeViewMode,
}: Pick<
  CatalogWorkspaceProps,
  | 'activePage'
  | 'collections'
  | 'filtersOpen'
  | 'pageTitle'
  | 'viewMode'
  | 'onChangeFiltersOpen'
  | 'onChangeViewMode'
>) {
  return (
    <section className="utility-panel">
      <h1>{pageTitle}</h1>
      {activePage === 'settings' ? (
        <CatalogSettings
          filtersOpen={filtersOpen}
          viewMode={viewMode}
          onChangeFiltersOpen={onChangeFiltersOpen}
          onChangeViewMode={onChangeViewMode}
        />
      ) : activePage === 'alerts' ? (
        <AlertsPanel watchlistSlugs={collections.watchlist} />
      ) : activePage === 'about' ? (
        <RatingExplainer />
      ) : null}
    </section>
  )
}

function CatalogHeading({
  activePage,
  activePreset,
  filters,
  headingTitle,
  isCuratedView,
  pageTitle,
  onApplyFilters,
  onChangeFilters,
}: Pick<
  CatalogWorkspaceProps,
  | 'activePage'
  | 'activePreset'
  | 'filters'
  | 'pageTitle'
  | 'onApplyFilters'
  | 'onChangeFilters'
> & {
  headingTitle: string
  isCuratedView: boolean
}) {
  if (!isCuratedView) {
    return (
      <div className="page-heading page-heading-catalog">
        <h1>Game rankings</h1>
        <p>
          Four-source ratings with current compatibility, playtime and price
          context.
        </p>
      </div>
    )
  }

  return (
    <div className="page-heading">
      <h1>{headingTitle}</h1>
      {activePreset === 'best-of-year' ? (
        <div className="year-picker" role="group" aria-label="Select year">
          {BEST_OF_YEAR_RANGE.map((year) => (
            <button
              key={year}
              type="button"
              className={filters.yearMin === year ? 'is-active' : ''}
              onClick={() => {
                onChangeFilters((current) => ({
                  ...current,
                  yearMin: year,
                  yearMax: year,
                }))
                onApplyFilters()
              }}
            >
              {year === CURRENT_YEAR ? `${year} · So Far` : String(year)}
            </button>
          ))}
        </div>
      ) : null}
      <p>
        {describeCatalogPage(
          activePreset,
          activePage,
          filters.yearMin,
          pageTitle,
        )}
      </p>
    </div>
  )
}

function GameResults({
  activePage,
  collectionSets,
  error,
  isLoading,
  isLoadingMore,
  loaderRef,
  pageTitle,
  viewMode,
  visibleGames,
  onBrowseCatalog,
  onFilterDeveloper,
  onFilterGenre,
  onFilterPublisher,
  onOpenDetail,
  onOpenTrailer,
  onToggleCollection,
}: Pick<
  CatalogWorkspaceProps,
  | 'activePage'
  | 'collectionSets'
  | 'error'
  | 'isLoading'
  | 'isLoadingMore'
  | 'loaderRef'
  | 'pageTitle'
  | 'viewMode'
  | 'visibleGames'
  | 'onBrowseCatalog'
  | 'onFilterDeveloper'
  | 'onFilterGenre'
  | 'onFilterPublisher'
  | 'onOpenDetail'
  | 'onOpenTrailer'
  | 'onToggleCollection'
>) {
  return (
    <>
      {error ? <p className="status status-error">{error}</p> : null}
      {isLoading ? (
        <div className={`game-list game-list-${viewMode}`} aria-hidden="true">
          {Array.from({ length: SKELETON_CARD_COUNT }, (_, index) => (
            <div key={index} className="skeleton-card" />
          ))}
        </div>
      ) : null}
      {!isLoading && visibleGames.length === 0 ? (
        <CatalogEmptyState
          activePage={activePage}
          pageTitle={pageTitle}
          onBrowseCatalog={onBrowseCatalog}
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
            onOpenDetail={onOpenDetail}
            onOpenTrailer={onOpenTrailer}
            onFilterDeveloper={onFilterDeveloper}
            onFilterGenre={onFilterGenre}
            onFilterPublisher={onFilterPublisher}
            onToggleCollection={onToggleCollection}
          />
        ))}
      </div>
      <div ref={loaderRef} className="scroll-sentinel" aria-hidden="true">
        {isLoadingMore ? <p className="status">Loading more…</p> : null}
      </div>
    </>
  )
}

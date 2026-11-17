import { CURRENT_YEAR, collectionPageMap, findPreset, utilityNavItems } from '../../catalog/config'
import type { GameSort } from '../../types/game'
import { ActiveFilterChips } from '../ActiveFilterChips'
import { CatalogToolbar } from '../CatalogToolbar'
import { FilterBar } from '../FilterBar'
import { GuestListNotice } from '../GuestListNotice'
import { CatalogHeading } from './CatalogHeading'
import { CatalogMasthead } from './CatalogMasthead'
import { GameResults } from './GameResults'
import type { CatalogWorkspaceProps } from './types'
import { UtilityPanel } from './UtilityPanel'

export function CatalogWorkspace(props: CatalogWorkspaceProps) {
  const isUtilityPage = utilityNavItems.some((item) => item.id === props.activePage)
  const isCuratedView = props.activePage !== 'catalog' || props.activePreset !== null
  const headingTitle =
    props.activePreset && props.activePreset !== 'best-of-year'
      ? (findPreset(props.activePreset)?.label ?? props.pageTitle)
      : props.pageTitle

  return (
    <main
      id="main-content"
      className={`workspace ${props.mastheadVisible ? 'masthead-open' : 'masthead-collapsed'}`}
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
        <CatalogBody {...props} headingTitle={headingTitle} isCuratedView={isCuratedView} />
      )}
    </main>
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
  const filterBarKey = `${props.pendingApply}-${props.facets.years.at(-1) ?? 1970}-${
    props.facets.years[0] ?? CURRENT_YEAR
  }`

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
      {props.activePage in collectionPageMap ? <GuestListNotice subject="list" /> : null}
      <ActiveFilterChips
        filters={props.filters}
        onClearDealMode={props.onClearDealMode}
        onClearFilter={props.onClearFilter}
      />
      {props.filtersOpen ? (
        <FilterBar
          key={filterBarKey}
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
        deferredCardCount={props.deferredCardCount}
        error={props.error}
        isLoading={props.isLoading}
        isLoadingMore={props.isLoadingMore}
        loadMoreError={props.loadMoreError}
        loaderRef={props.loaderRef}
        pageTitle={props.pageTitle}
        query={props.filters.q.trim()}
        viewMode={props.viewMode}
        visibleGames={props.visibleGames}
        onBrowseCatalog={props.onBrowseCatalog}
        onClearSearch={() => props.onChangeFilters((current) => ({ ...current, q: '' }))}
        onFilterDeveloper={props.onFilterDeveloper}
        onFilterGenre={props.onFilterGenre}
        onFilterPublisher={props.onFilterPublisher}
        onOpenDetail={props.onOpenDetail}
        onOpenTrailer={props.onOpenTrailer}
        onRetryError={props.onRetryError}
        onRetryLoadMore={props.onRetryLoadMore}
        onToggleCollection={props.onToggleCollection}
      />
    </section>
  )
}

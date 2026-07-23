import { AlertsPanel } from '../alerts/AlertsPanel'
import { CatalogSettings } from '../CatalogSettings'
import { RatingExplainer } from '../RatingExplainer'
import type { WorkspaceProps } from './types'

type UtilityPanelProps = WorkspaceProps<
  | 'activePage'
  | 'collections'
  | 'filtersOpen'
  | 'pageTitle'
  | 'viewMode'
  | 'onChangeFiltersOpen'
  | 'onChangeViewMode'
>

export function UtilityPanel({
  activePage,
  collections,
  filtersOpen,
  pageTitle,
  viewMode,
  onChangeFiltersOpen,
  onChangeViewMode,
}: UtilityPanelProps) {
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

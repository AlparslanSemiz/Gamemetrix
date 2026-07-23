import { Grid2X2, List, SlidersHorizontal } from 'lucide-react'
import type { ViewMode } from './CatalogToolbar'

interface CatalogSettingsProps {
  filtersOpen: boolean
  viewMode: ViewMode
  onChangeFiltersOpen: (open: boolean) => void
  onChangeViewMode: (mode: ViewMode) => void
}

export function CatalogSettings({
  filtersOpen,
  viewMode,
  onChangeFiltersOpen,
  onChangeViewMode,
}: CatalogSettingsProps) {
  return (
    <div className="settings-grid">
      <section className="settings-card">
        <h2>Catalog Layout</h2>
        <div className="settings-segmented" role="group" aria-label="Catalog layout">
          <button
            type="button"
            className={viewMode === 'list' ? 'is-active' : ''}
            onClick={() => onChangeViewMode('list')}
          >
            <List size={16} aria-hidden="true" />
            <span>List</span>
          </button>
          <button
            type="button"
            className={viewMode === 'grid' ? 'is-active' : ''}
            onClick={() => onChangeViewMode('grid')}
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
            onClick={() => onChangeFiltersOpen(true)}
          >
            <SlidersHorizontal size={16} aria-hidden="true" />
            <span>Open</span>
          </button>
          <button
            type="button"
            className={!filtersOpen ? 'is-active' : ''}
            onClick={() => onChangeFiltersOpen(false)}
          >
            <List size={16} aria-hidden="true" />
            <span>Compact</span>
          </button>
        </div>
      </section>
    </div>
  )
}

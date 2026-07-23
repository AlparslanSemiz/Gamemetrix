import { ArrowDown, ArrowUp, Grid2X2, List, SlidersHorizontal } from 'lucide-react'
import { sortOptions } from '../catalog/config'
import type { GameSort } from '../types/game'

export type ViewMode = 'list' | 'grid'

interface CatalogToolbarProps {
  direction: 'asc' | 'desc'
  filtersOpen: boolean
  sort: GameSort
  viewMode: ViewMode
  onToggleDirection: () => void
  onToggleFilters: () => void
  onChangeSort: (sort: GameSort) => void
  onChangeViewMode: (mode: ViewMode) => void
}

export function CatalogToolbar({
  direction,
  filtersOpen,
  sort,
  viewMode,
  onToggleDirection,
  onToggleFilters,
  onChangeSort,
  onChangeViewMode,
}: CatalogToolbarProps) {
  const directionLabel = direction === 'desc' ? 'High to low' : 'Low to high'

  return (
    <div className="list-toolbar">
      <button
        type="button"
        className={`filter-toggle-button${filtersOpen ? ' is-active' : ''}`}
        onClick={onToggleFilters}
        title={filtersOpen ? 'Hide filters' : 'Show filters'}
      >
        <SlidersHorizontal size={15} aria-hidden="true" />
        <span>Filters</span>
      </button>
      <div className="sort-label">
        <span>Sort By:</span>
        <select
          aria-label="Sort games"
          value={sort}
          onChange={(event) => onChangeSort(event.target.value as GameSort)}
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
          title={directionLabel}
          onClick={onToggleDirection}
        >
          {direction === 'desc' ? (
            <ArrowDown size={15} aria-hidden="true" />
          ) : (
            <ArrowUp size={15} aria-hidden="true" />
          )}
        </button>
        <span className="sort-direction-text">{directionLabel}</span>
      </div>
      <div className="view-toggle" aria-label="View mode">
        <button
          type="button"
          className={viewMode === 'list' ? 'is-active' : ''}
          onClick={() => onChangeViewMode('list')}
          title="List view"
        >
          <List size={17} aria-hidden="true" />
        </button>
        <button
          type="button"
          className={viewMode === 'grid' ? 'is-active' : ''}
          onClick={() => onChangeViewMode('grid')}
          title="Grid view"
        >
          <Grid2X2 size={16} aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}

import { Search } from 'lucide-react'

import { formatRoundedThousands } from '../../catalog/config'
import type { WorkspaceProps } from './types'

const SEARCH_ICON_SIZE = 18
const MAX_SEARCH_LENGTH = 120

type CatalogMastheadProps = WorkspaceProps<
  | 'catalogTotal'
  | 'filters'
  | 'libraryTotal'
  | 'mastheadRef'
  | 'onBrowseCatalog'
  | 'onChangeFilters'
  | 'onFocusSearch'
> & { visible: boolean }

export function CatalogMasthead({
  catalogTotal,
  filters,
  libraryTotal,
  mastheadRef,
  visible,
  onBrowseCatalog,
  onChangeFilters,
  onFocusSearch,
}: CatalogMastheadProps) {
  return (
    <header ref={mastheadRef} className={`masthead ${visible ? 'is-visible' : 'is-hidden'}`}>
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
          maxLength={MAX_SEARCH_LENGTH}
          value={filters.q}
          onFocus={onFocusSearch}
          onChange={(event) => {
            onChangeFilters((current) => ({ ...current, q: event.target.value }))
          }}
          aria-label="Search games by title"
        />
        <div className="masthead-search-meta">
          <span>{formatRoundedThousands(libraryTotal || catalogTotal)} games</span>
          <Search size={SEARCH_ICON_SIZE} aria-hidden="true" />
        </div>
      </div>
    </header>
  )
}

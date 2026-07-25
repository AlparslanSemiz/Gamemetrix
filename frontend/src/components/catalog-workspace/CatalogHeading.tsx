import {
  BEST_OF_YEAR_RANGE,
  CURRENT_YEAR,
  describeCatalogPage,
} from '../../catalog/config'
import type { WorkspaceProps } from './types'

type CatalogHeadingProps = WorkspaceProps<
  'activePage' | 'activePreset' | 'filters' | 'pageTitle' | 'onApplyFilters' | 'onChangeFilters'
> & {
  headingTitle: string
  isCuratedView: boolean
}

export function CatalogHeading({
  activePage,
  activePreset,
  filters,
  headingTitle,
  isCuratedView,
  pageTitle,
  onApplyFilters,
  onChangeFilters,
}: CatalogHeadingProps) {
  if (!isCuratedView) {
    return (
      <div className="page-heading page-heading-catalog">
        <h1>Game scores and PC compatibility rankings</h1>
        <p>
          GameMetrix compares four named rating sources with Linux compatibility,
          playtime and current PC price context.
        </p>
      </div>
    )
  }

  return (
    <div className="page-heading">
      <h1>{headingTitle}</h1>
      {activePreset === 'best-of-year' ? (
        <YearPicker
          selectedYear={filters.yearMin}
          onSelectYear={(year) => {
            onChangeFilters((current) => ({ ...current, yearMin: year, yearMax: year }))
            onApplyFilters()
          }}
        />
      ) : null}
      <p>{describeCatalogPage(activePreset, activePage, filters.yearMin, pageTitle)}</p>
    </div>
  )
}

function YearPicker({
  selectedYear,
  onSelectYear,
}: {
  selectedYear: number | null
  onSelectYear: (year: number) => void
}) {
  return (
    <div className="year-picker" role="group" aria-label="Select year">
      {BEST_OF_YEAR_RANGE.map((year) => (
        <button
          key={year}
          type="button"
          className={selectedYear === year ? 'is-active' : ''}
          onClick={() => onSelectYear(year)}
        >
          {year === CURRENT_YEAR ? `${year} · So Far` : String(year)}
        </button>
      ))}
    </div>
  )
}

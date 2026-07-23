import type { GameFilters } from '../types/game'

export type ClearableFilterKey = 'developer' | 'publisher' | 'genre' | 'platform'

const CLEARABLE_FILTERS: Array<{ key: ClearableFilterKey; label: string }> = [
  { key: 'developer', label: 'Developer' },
  { key: 'publisher', label: 'Publisher' },
  { key: 'genre', label: 'Genre' },
  { key: 'platform', label: 'Platform' },
]

interface ActiveFilterChipsProps {
  filters: GameFilters
  onClearDealMode: () => void
  onClearFilter: (key: ClearableFilterKey) => void
}

export function ActiveFilterChips({ filters, onClearDealMode, onClearFilter }: ActiveFilterChipsProps) {
  const hasDealFilter = filters.dealMode !== 'all'
  const activeChips = CLEARABLE_FILTERS.filter(({ key }) => filters[key])
  if (!hasDealFilter && activeChips.length === 0) return null

  return (
    <div className="active-filter-row" aria-label="Active filters">
      {hasDealFilter ? (
        <button type="button" onClick={onClearDealMode}>
          Deal: {filters.dealMode === 'best' ? 'Best Deals' : 'Free Games'} ×
        </button>
      ) : null}
      {activeChips.map(({ key, label }) => (
        <button type="button" key={key} onClick={() => onClearFilter(key)}>
          {label}: {filters[key]} ×
        </button>
      ))}
    </div>
  )
}

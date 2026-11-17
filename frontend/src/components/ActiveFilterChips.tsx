import { activeFilterChips } from '../catalog/filterChips'
import type { GameFilters } from '../types/game'

interface ActiveFilterChipsProps {
  filters: GameFilters
  onClearDealMode: () => void
  onClearFilter: (reset: Partial<GameFilters>) => void
}

export function ActiveFilterChips({ filters, onClearDealMode, onClearFilter }: ActiveFilterChipsProps) {
  const hasDealFilter = filters.dealMode !== 'all'
  const chips = activeFilterChips(filters)
  if (!hasDealFilter && chips.length === 0) return null

  return (
    <div className="active-filter-row" aria-label="Active filters">
      {hasDealFilter ? (
        <button type="button" onClick={onClearDealMode}>
          Deal: {filters.dealMode === 'best' ? 'Best Deals' : 'Free Games'} ×
        </button>
      ) : null}
      {chips.map((chip) => (
        <button type="button" key={chip.id} data-chip={chip.id} onClick={() => onClearFilter(chip.reset)}>
          {chip.label} ×
        </button>
      ))}
    </div>
  )
}

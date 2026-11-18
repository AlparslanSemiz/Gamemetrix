import type { GameFilters } from '../types/game'
import { formatNumber } from '../utils/format'
import { CURRENT_YEAR, DEFAULT_FILTERS } from './queryParams'

export interface FilterChip {
  id: string
  label: string
  /** Filter fields that return this chip's filter to its default. */
  reset: Partial<GameFilters>
}

function hoursLabel(min: number | null, max: number | null): string {
  if (min !== null && max !== null) return `${min}–${max} h`
  if (max !== null) return `≤ ${max} h`
  return `≥ ${min ?? 0} h`
}

function rangeLabel(min: number, max: number, floor: number, ceiling: number): string {
  if (min > floor && max < ceiling) return `${min}–${max}`
  return min > floor ? `${min}+` : `≤ ${max}`
}

const PLAYER_MODE_LABELS: Record<string, string> = {
  singleplayer: 'Single-player',
  multiplayer: 'Multiplayer',
  coop: 'Co-op',
}

/** One chip per active (non-default) filter field, so nothing filters invisibly. */
export function activeFilterChips(filters: GameFilters): FilterChip[] {
  const chips: FilterChip[] = []
  if (filters.q.trim()) chips.push({ id: 'q', label: `Search: “${filters.q.trim()}”`, reset: { q: '' } })
  const text = [
    ['developer', 'Developer'],
    ['publisher', 'Publisher'],
    ['genre', 'Genre'],
    ['platform', 'Platform'],
  ] as const
  for (const [key, label] of text) {
    if (filters[key]) chips.push({ id: key, label: `${label}: ${filters[key]}`, reset: { [key]: '' } })
  }
  if (filters.yearMin > DEFAULT_FILTERS.yearMin || filters.yearMax < CURRENT_YEAR) {
    const label = filters.yearMin === filters.yearMax
      ? String(filters.yearMin)
      : rangeLabel(filters.yearMin, filters.yearMax, DEFAULT_FILTERS.yearMin, CURRENT_YEAR)
    chips.push({ id: 'year', label: `Year: ${label}`, reset: { yearMin: DEFAULT_FILTERS.yearMin, yearMax: DEFAULT_FILTERS.yearMax } })
  }
  if (filters.minScore > 0 || filters.maxScore < 100) {
    chips.push({ id: 'score', label: `Score: ${rangeLabel(filters.minScore, filters.maxScore, 0, 100)}`, reset: { minScore: 0, maxScore: 100 } })
  }
  if (filters.minRatings > 0 || filters.maxRatings > 0) {
    const label = filters.maxRatings > 0 && filters.minRatings > 0
      ? `${formatNumber(filters.minRatings)}–${formatNumber(filters.maxRatings)}`
      : filters.minRatings > 0
        ? `${formatNumber(filters.minRatings)}+`
        : `≤ ${formatNumber(filters.maxRatings)}`
    chips.push({ id: 'ratings', label: `Ratings: ${label}`, reset: { minRatings: 0, maxRatings: 0 } })
  }
  if (filters.minLiveSources > 0 || filters.requireCritic) {
    const parts = [
      filters.minLiveSources > 0 ? `${filters.minLiveSources}+ sources` : '',
      filters.requireCritic ? 'critic score' : '',
    ].filter(Boolean)
    chips.push({ id: 'sources', label: `Sources: ${parts.join(', ')}`, reset: { minLiveSources: 0, requireCritic: false } })
  }
  if (filters.playtimeMinHours !== null || filters.playtimeMaxHours !== null) {
    chips.push({
      id: 'playtime',
      label: `Playtime: ${hoursLabel(filters.playtimeMinHours, filters.playtimeMaxHours)}`,
      reset: { playtimeMinHours: null, playtimeMaxHours: null },
    })
  }
  if (filters.playerMode) {
    chips.push({ id: 'mode', label: `Mode: ${PLAYER_MODE_LABELS[filters.playerMode] ?? filters.playerMode}`, reset: { playerMode: '' } })
  }
  if (filters.hasAward) chips.push({ id: 'award', label: 'Award winners', reset: { hasAward: false } })
  return chips
}

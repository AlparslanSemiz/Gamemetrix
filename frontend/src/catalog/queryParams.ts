// Pure, environment-free catalog query logic shared by the SSR loader, the
// browser fetches and the URL <-> filter state sync. Nothing here may touch
// window, import.meta.env or the clock beyond the UTC year.
import type { GameFilters, GameSort, PlayerMode, SortDirection } from '../types/game'
import { currentUtcYear } from '../utils/format'

const EARLIEST_YEAR = 1970
export const CURRENT_YEAR = currentUtcYear()

export const DEFAULT_FILTERS: GameFilters = {
  q: '',
  genre: '',
  platform: '',
  developer: '',
  publisher: '',
  yearMin: EARLIEST_YEAR,
  yearMax: CURRENT_YEAR,
  minScore: 0,
  maxScore: 100,
  minRatings: 0,
  maxRatings: 0,
  minLiveSources: 0,
  requireCritic: false,
  hasAward: false,
  dealMode: 'all',
  playerMode: '',
  playtimeMinHours: null,
  playtimeMaxHours: null,
  sort: 'rank_score',
  direction: 'desc',
}

export function buildCatalogParams(filters: GameFilters, limit: number, offset: number): URLSearchParams {
  const params = new URLSearchParams()

  if (filters.q.trim()) params.set('q', filters.q.trim())
  if (filters.genre) params.set('genre', filters.genre)
  if (filters.platform) params.set('platform', filters.platform)
  if (filters.developer) params.set('developer', filters.developer)
  if (filters.publisher) params.set('publisher', filters.publisher)
  const yearLo = Math.min(filters.yearMin, filters.yearMax)
  const yearHi = Math.max(filters.yearMin, filters.yearMax)
  if (yearLo > EARLIEST_YEAR) params.set('year_min', String(yearLo))
  if (yearHi < CURRENT_YEAR) params.set('year_max', String(yearHi))
  const scoreLo = Math.min(filters.minScore, filters.maxScore)
  const scoreHi = Math.max(filters.minScore, filters.maxScore)
  if (scoreLo > 0) params.set('min_score', String(scoreLo))
  if (scoreHi < 100) params.set('max_score', String(scoreHi))
  if (filters.minRatings > 0) params.set('min_ratings', String(filters.minRatings))
  if (filters.maxRatings > 0) params.set('max_ratings', String(filters.maxRatings))
  if (filters.minLiveSources > 0) params.set('min_live_sources', String(filters.minLiveSources))
  if (filters.requireCritic) params.set('require_critic', 'true')
  if (filters.hasAward) params.set('has_award', 'true')
  if (filters.dealMode !== 'all') params.set('deal', filters.dealMode)
  if (filters.playerMode) params.set('player_mode', filters.playerMode)
  if (filters.playtimeMinHours !== null) params.set('playtime_min_hours', String(filters.playtimeMinHours))
  if (filters.playtimeMaxHours !== null) params.set('playtime_max_hours', String(filters.playtimeMaxHours))
  params.set('sort', filters.sort)
  params.set('direction', filters.direction)
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  return params
}

// ---------------------------------------------------------------------------
// URL <-> filters. The address bar carries every non-default filter so a result
// list can be shared, reloaded and navigated with back/forward. Non-filter
// params (`view`) are left alone.
// ---------------------------------------------------------------------------

const SORTS: ReadonlySet<GameSort> = new Set([
  'rank_score', 'metrix_score', 'release_year', 'title', 'critic_score', 'user_score',
  'metacritic_score', 'opencritic_score', 'steam_score', 'review_count',
])
const PLAYER_MODES: ReadonlySet<string> = new Set(['singleplayer', 'multiplayer', 'coop'])
const MAX_TEXT_LENGTH = 120

/** Every query key owned by the filter state. */
const FILTER_URL_KEYS = [
  'q', 'genre', 'platform', 'developer', 'publisher', 'year', 'year_min', 'year_max',
  'min_score', 'max_score', 'min_ratings', 'max_ratings', 'min_sources', 'critic', 'award',
  'deal', 'mode', 'pt_min', 'pt_max', 'sort', 'dir',
] as const

function text(params: URLSearchParams, key: string): string | undefined {
  const value = params.get(key)?.trim().slice(0, MAX_TEXT_LENGTH)
  return value || undefined
}

function integer(params: URLSearchParams, key: string, min: number, max: number): number | undefined {
  const raw = params.get(key)
  if (raw === null || raw.trim() === '') return undefined
  const value = Number(raw)
  return Number.isInteger(value) && value >= min && value <= max ? value : undefined
}

export function readUrlFilters(search: string): Partial<GameFilters> {
  const params = new URLSearchParams(search)
  const next: Partial<GameFilters> = {}
  const q = text(params, 'q')
  const genre = text(params, 'genre')
  const platform = text(params, 'platform')
  const developer = text(params, 'developer')
  const publisher = text(params, 'publisher')
  if (q) next.q = q
  if (genre) next.genre = genre
  if (platform) next.platform = platform
  if (developer) next.developer = developer
  if (publisher) next.publisher = publisher

  // `year` is the older single-year deep link used by the detail and ranking pages.
  const year = integer(params, 'year', EARLIEST_YEAR + 1, CURRENT_YEAR)
  const yearMin = integer(params, 'year_min', EARLIEST_YEAR, CURRENT_YEAR) ?? year
  const yearMax = integer(params, 'year_max', EARLIEST_YEAR, CURRENT_YEAR) ?? year
  if (yearMin !== undefined) next.yearMin = yearMin
  if (yearMax !== undefined) next.yearMax = yearMax

  const minScore = integer(params, 'min_score', 0, 100)
  const maxScore = integer(params, 'max_score', 0, 100)
  if (minScore !== undefined) next.minScore = minScore
  if (maxScore !== undefined) next.maxScore = maxScore
  const minRatings = integer(params, 'min_ratings', 0, 100_000_000)
  const maxRatings = integer(params, 'max_ratings', 0, 100_000_000)
  if (minRatings !== undefined) next.minRatings = minRatings
  if (maxRatings !== undefined) next.maxRatings = maxRatings
  const sources = integer(params, 'min_sources', 0, 4)
  if (sources !== undefined) next.minLiveSources = sources
  if (params.get('critic') === '1') next.requireCritic = true
  if (params.get('award') === '1') next.hasAward = true
  const deal = params.get('deal')
  if (deal === 'best' || deal === 'free') next.dealMode = deal
  const mode = params.get('mode')
  if (mode && PLAYER_MODES.has(mode)) next.playerMode = mode as PlayerMode
  const ptMin = integer(params, 'pt_min', 0, 10_000)
  const ptMax = integer(params, 'pt_max', 0, 10_000)
  if (ptMin !== undefined) next.playtimeMinHours = ptMin
  if (ptMax !== undefined) next.playtimeMaxHours = ptMax
  const sort = params.get('sort')
  if (sort && SORTS.has(sort as GameSort)) next.sort = sort as GameSort
  const dir = params.get('dir')
  if (dir === 'asc' || dir === 'desc') next.direction = dir as SortDirection
  return next
}

/** The filter-owned part of the query string for `filters`, defaults omitted. */
function filtersToUrlParams(filters: GameFilters): URLSearchParams {
  const params = new URLSearchParams()
  const d = DEFAULT_FILTERS
  if (filters.q.trim()) params.set('q', filters.q.trim())
  if (filters.genre) params.set('genre', filters.genre)
  if (filters.platform) params.set('platform', filters.platform)
  if (filters.developer) params.set('developer', filters.developer)
  if (filters.publisher) params.set('publisher', filters.publisher)
  if (filters.yearMin !== d.yearMin) params.set('year_min', String(filters.yearMin))
  if (filters.yearMax !== d.yearMax) params.set('year_max', String(filters.yearMax))
  if (filters.minScore !== d.minScore) params.set('min_score', String(filters.minScore))
  if (filters.maxScore !== d.maxScore) params.set('max_score', String(filters.maxScore))
  if (filters.minRatings > 0) params.set('min_ratings', String(filters.minRatings))
  if (filters.maxRatings > 0) params.set('max_ratings', String(filters.maxRatings))
  if (filters.minLiveSources > 0) params.set('min_sources', String(filters.minLiveSources))
  if (filters.requireCritic) params.set('critic', '1')
  if (filters.hasAward) params.set('award', '1')
  if (filters.dealMode !== 'all') params.set('deal', filters.dealMode)
  if (filters.playerMode) params.set('mode', filters.playerMode)
  if (filters.playtimeMinHours !== null) params.set('pt_min', String(filters.playtimeMinHours))
  if (filters.playtimeMaxHours !== null) params.set('pt_max', String(filters.playtimeMaxHours))
  if (filters.sort !== d.sort) params.set('sort', filters.sort)
  if (filters.direction !== d.direction) params.set('dir', filters.direction)
  return params
}

/** `search` with its filter keys replaced by those of `filters`; other keys survive. */
export function mergeFiltersIntoSearch(search: string, filters: GameFilters): string {
  const params = new URLSearchParams(search)
  for (const key of FILTER_URL_KEYS) params.delete(key)
  for (const [key, value] of filtersToUrlParams(filters)) params.set(key, value)
  const result = params.toString()
  return result ? `?${result}` : ''
}

/** Compares the filter-owned parts of two query strings, ignoring order and `view`. */
export function sameFilterSearch(a: string, b: string): boolean {
  const pick = (search: string) => {
    const params = new URLSearchParams(search)
    const picked = new URLSearchParams()
    for (const key of FILTER_URL_KEYS) {
      const value = params.get(key)
      if (value !== null) picked.set(key, value)
    }
    picked.sort()
    return picked.toString()
  }
  return pick(a) === pick(b)
}

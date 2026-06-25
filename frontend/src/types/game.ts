export interface SourceScore {
  source: string
  score: number
  scale: number
  status?: 'live' | 'mock' | 'unavailable'
  detail?: string
  refreshed_at?: string
  review_count?: number
}

export interface Game {
  id: number
  title: string
  slug: string
  summary: string
  cover_url: string
  release_date: string
  release_year: number
  metrix_score: number
  critic_score: number
  user_score: number
  genres: string[]
  platforms: string[]
  source_scores: SourceScore[]
  developer?: string | null
  publisher?: string | null
  playtime_minutes: number
}

export interface GameListResponse {
  games: Game[]
  total: number
}

export interface Facets {
  genres: string[]
  years: number[]
  platforms: string[]
}

export interface ProviderStatus {
  source: string
  status: string
  detail: string
}

export type GameSort =
  | 'metrix_score'
  | 'release_year'
  | 'title'
  | 'critic_score'
  | 'user_score'
  | 'metacritic_score'
  | 'opencritic_score'
  | 'steam_score'
  | 'review_count'

export type SortDirection = 'asc' | 'desc'

export interface GameFilters {
  q: string
  genre: string
  platform: string
  developer: string
  publisher: string
  yearMin: number
  yearMax: number
  minScore: number
  maxScore: number
  minRatings: number
  minLiveSources: number
  requireCritic: boolean
  sort: GameSort
  direction: SortDirection
}

export interface ScoreWeightsResponse {
  weights: Record<string, number>
}

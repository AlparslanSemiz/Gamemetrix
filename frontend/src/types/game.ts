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
  metacritic_score?: number | null
  image_url?: string | null
  ratings_refreshed_at?: string | null
  content_type: string
  live_primary_source_count: number
  applicable_source_count?: number
  applicable_sources?: string[]
  confidence_level: string
  score_profile: string
  popularity_label?: string | null
  metrix_score: number
  critic_score: number
  user_score: number
  genres: string[]
  platforms: string[]
  source_scores: SourceScore[]
  developer?: string | null
  publisher?: string | null
  playtime_minutes: number
  award_count: number
  award_nominations: number
  goty_year?: number | null
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
  maxRatings: number
  minLiveSources: number
  requireCritic: boolean
  hasAward: boolean
  sort: GameSort
  direction: SortDirection
}

export interface ScoreWeightsResponse {
  weights: Record<string, number>
}

export interface TrailerResponse {
  video_id: string | null
  watch_url: string | null
}

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
  summary_short?: string | null
  cover_url: string
  release_date: string
  release_year: number
  early_access_date?: string | null
  official_release_date?: string | null
  metacritic_score?: number | null
  image_url?: string | null
  ratings_refreshed_at?: string | null
  metadata_refreshed_at?: string | null
  content_type: string
  live_primary_source_count: number
  applicable_source_count?: number
  applicable_sources?: string[]
  confidence_level: string
  data_strength: string
  score_profile: string
  popularity_label?: string | null
  metrix_score: number
  rank_score: number
  is_rankable: boolean
  rank_exclusion_reason?: string | null
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
  awards: string[]
  screenshots: string[]
  system_requirements: SystemRequirement[]
  dlcs: RelatedGame[]
  similar_games: RelatedGame[]
  price_snapshots?: PriceSnapshot[]
}

export interface SystemRequirement {
  platform: string
  minimum: string
  recommended: string
}

export interface RelatedGame {
  id?: number | string | null
  title: string
  slug?: string | null
  release_date?: string | null
  release_year?: number | null
  cover_url?: string | null
  metacritic_score?: number | null
  rating?: number | null
  url?: string | null
  type?: string | null
}

export interface PriceSnapshot {
  source: string
  store: string
  platform?: string | null
  region: string
  currency: string
  list_price?: number | null
  sale_price?: number | null
  discount_percent?: number | null
  historical_low?: number | null
  historical_low_date?: string | null
  sale_end_date?: string | null
  is_free: boolean
  is_subscription_included: boolean
  subscription_service?: string | null
  url?: string | null
  fetched_at: string
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
  | 'rank_score'
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

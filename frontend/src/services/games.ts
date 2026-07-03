import type {
  Facets,
  Game,
  GameFilters,
  GameListResponse,
  ProviderStatus,
  ScoreWeightsResponse,
  TrailerResponse,
} from '../types/game'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

const CURRENT_YEAR = new Date().getFullYear()

export async function getGames(
  filters: GameFilters,
  limit = 24,
  offset = 0,
): Promise<GameListResponse> {
  const params = new URLSearchParams()

  if (filters.q.trim()) params.set('q', filters.q.trim())
  if (filters.genre) params.set('genre', filters.genre)
  if (filters.platform) params.set('platform', filters.platform)
  if (filters.developer) params.set('developer', filters.developer)
  if (filters.publisher) params.set('publisher', filters.publisher)
  const yearLo = Math.min(filters.yearMin, filters.yearMax)
  const yearHi = Math.max(filters.yearMin, filters.yearMax)
  if (yearLo > 1970) params.set('year_min', String(yearLo))
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
  params.set('sort', filters.sort)
  params.set('direction', filters.direction)
  params.set('limit', String(limit))
  params.set('offset', String(offset))

  const response = await fetch(`${API_BASE_URL}/api/games?${params.toString()}`)
  if (!response.ok) throw new Error('Failed to fetch games')
  return response.json()
}

export async function getGameBySlug(slug: string): Promise<Game> {
  const response = await fetch(`${API_BASE_URL}/api/games/${slug}`)
  if (!response.ok) throw new Error('Game not found')
  return response.json()
}

export async function getSimilarGames(slug: string, limit = 10): Promise<GameListResponse> {
  const response = await fetch(`${API_BASE_URL}/api/games/${slug}/similar?limit=${limit}`)
  if (!response.ok) throw new Error('Failed to fetch similar games')
  return response.json()
}

export async function getFacets(): Promise<Facets> {
  const response = await fetch(`${API_BASE_URL}/api/facets`)
  if (!response.ok) throw new Error('Failed to fetch facets')
  return response.json()
}

export async function getIntegrationStatus(): Promise<ProviderStatus[]> {
  const response = await fetch(`${API_BASE_URL}/api/integrations/status`)
  if (!response.ok) throw new Error('Failed to fetch integration status')
  return response.json()
}

export async function refreshGameScores(slug: string): Promise<Game> {
  const response = await fetch(`${API_BASE_URL}/api/games/${slug}/refresh-scores`, {
    method: 'POST',
  })
  if (!response.ok) throw new Error('Failed to refresh scores')
  return response.json()
}

export async function getGameTrailer(slug: string): Promise<TrailerResponse> {
  const response = await fetch(`${API_BASE_URL}/api/games/${slug}/trailer`)
  if (!response.ok) throw new Error('Failed to fetch trailer')
  return response.json()
}

export async function fetchGameScreenshots(slug: string): Promise<Game> {
  const response = await fetch(`${API_BASE_URL}/api/games/${slug}/fetch-screenshots`, {
    method: 'POST',
  })
  if (!response.ok) throw new Error('Failed to fetch screenshots')
  return response.json()
}

export async function fetchGameSystemRequirements(slug: string): Promise<Game> {
  const response = await fetch(`${API_BASE_URL}/api/games/${slug}/fetch-system-requirements`, {
    method: 'POST',
  })
  if (!response.ok) throw new Error('Failed to fetch system requirements')
  return response.json()
}

export async function fetchGamePrices(slug: string): Promise<Game> {
  const response = await fetch(`${API_BASE_URL}/api/games/${slug}/fetch-prices`, {
    method: 'POST',
  })
  if (!response.ok) throw new Error('Failed to fetch prices')
  return response.json()
}

export async function getScoreWeights(): Promise<ScoreWeightsResponse> {
  const response = await fetch(`${API_BASE_URL}/api/score-weights`)
  if (!response.ok) throw new Error('Failed to fetch score weights')
  return response.json()
}

export async function updateScoreWeights(
  weights: Record<string, number>,
): Promise<ScoreWeightsResponse> {
  const response = await fetch(`${API_BASE_URL}/api/score-weights`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ weights }),
  })
  if (!response.ok) throw new Error('Failed to update score weights')
  return response.json()
}

export async function getRateLimits(): Promise<Record<string, { remaining: number; limit: number }>> {
  const response = await fetch(`${API_BASE_URL}/api/rate-limits`)
  if (!response.ok) throw new Error('Failed to fetch rate limits')
  return response.json()
}

export async function refreshAllScores(force = false, concurrency = 3): Promise<{ status: string; message: string }> {
  const response = await fetch(
    `${API_BASE_URL}/api/ratings/refresh-all?force=${force}&concurrency=${concurrency}`,
    { method: 'POST' },
  )
  if (!response.ok) throw new Error('Failed to start refresh')
  return response.json()
}

export async function recalculateScores(): Promise<{ recalculated: number }> {
  const response = await fetch(`${API_BASE_URL}/api/score-weights/recalculate`, {
    method: 'POST',
  })
  if (!response.ok) throw new Error('Failed to recalculate scores')
  return response.json()
}

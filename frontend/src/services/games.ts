import type {
  Facets,
  CatalogGame,
  CatalogGameListResponse,
  Game,
  GameFilters,
  ScoreWeightsResponse,
  SeriesResponse,
  SimilarGamesResponse,
  TrailerResponse,
} from '../types/game'
import { buildCatalogParams } from '../catalog/queryParams'
import { API_BASE_URL } from './api'

const DEFAULT_CATALOG_REQUEST_TIMEOUT_MS = 12_000

function catalogRequestTimeoutMs(): number {
  const configured = Number(import.meta.env.VITE_CATALOG_REQUEST_TIMEOUT_MS)
  return Number.isFinite(configured) && configured > 0
    ? configured
    : DEFAULT_CATALOG_REQUEST_TIMEOUT_MS
}

function authHeaders(token?: string): HeadersInit | undefined {
  return token ? { Authorization: `Bearer ${token}` } : undefined
}

export async function getCatalogGames(
  filters: GameFilters,
  limit = 24,
  offset = 0,
  signal?: AbortSignal,
): Promise<CatalogGameListResponse> {
  const params = buildCatalogParams(filters, limit, offset)
  const controller = new AbortController()
  const abortFromCaller = () => controller.abort()
  if (signal?.aborted) controller.abort()
  signal?.addEventListener('abort', abortFromCaller, { once: true })
  const timeout = setTimeout(() => controller.abort(), catalogRequestTimeoutMs())
  try {
    const response = await fetch(`${API_BASE_URL}/api/catalog/games?${params.toString()}`, {
      signal: controller.signal,
    })
    if (!response.ok) throw new Error('Failed to fetch catalog games')
    return await response.json()
  } finally {
    clearTimeout(timeout)
    signal?.removeEventListener('abort', abortFromCaller)
  }
}

export async function getCatalogGamesBySlugs(
  slugs: string[],
  includePrices = false,
): Promise<CatalogGame[]> {
  if (slugs.length === 0) return []
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), catalogRequestTimeoutMs())
  try {
    const response = await fetch(
      `${API_BASE_URL}/api/catalog/games/batch?include_prices=${includePrices}`,
      {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slugs }),
      signal: controller.signal,
      },
    )
    if (!response.ok) throw new Error('Failed to fetch saved games')
    const payload = await response.json() as CatalogGameListResponse
    return payload.games
  } finally {
    clearTimeout(timeout)
  }
}

export async function getGameBySlug(
  slug: string,
  refreshMetadata = false,
  signal?: AbortSignal,
): Promise<Game> {
  const response = await fetch(
    `${API_BASE_URL}/api/games/${slug}?refresh=${refreshMetadata}`,
    { signal },
  )
  if (!response.ok) throw new Error('Game not found')
  return response.json()
}

export async function getSimilarGames(
  slug: string,
  limit = 10,
  signal?: AbortSignal,
): Promise<SimilarGamesResponse> {
  return relatedGamesRequest(
    `${API_BASE_URL}/api/games/${slug}/similar?limit=${limit}`,
    'similar games',
    signal,
  )
}

export async function getSeriesGames(
  slug: string,
  limit = 8,
  signal?: AbortSignal,
): Promise<SeriesResponse> {
  return relatedGamesRequest(
    `${API_BASE_URL}/api/games/${slug}/series?limit=${limit}`,
    'series games',
    signal,
  )
}

async function relatedGamesRequest<T>(
  url: string,
  label: string,
  externalSignal?: AbortSignal,
): Promise<T> {
  const controller = new AbortController()
  const abortFromExternal = () => controller.abort()
  externalSignal?.addEventListener('abort', abortFromExternal, { once: true })
  const timeout = setTimeout(() => controller.abort(), catalogRequestTimeoutMs())
  try {
    const response = await fetch(url, { signal: controller.signal })
    if (!response.ok) throw new Error(`Failed to fetch ${label}`)
    return await response.json() as T
  } finally {
    clearTimeout(timeout)
    externalSignal?.removeEventListener('abort', abortFromExternal)
  }
}

export async function getFacets(): Promise<Facets> {
  const response = await fetch(`${API_BASE_URL}/api/facets`)
  if (!response.ok) throw new Error('Failed to fetch facets')
  return response.json()
}

export async function getGameTrailer(
  slug: string,
  signal?: AbortSignal,
): Promise<TrailerResponse> {
  const response = await fetch(`${API_BASE_URL}/api/games/${slug}/trailer`, { signal })
  if (!response.ok) throw new Error('Failed to fetch trailer')
  return response.json()
}

export async function getScoreWeights(): Promise<ScoreWeightsResponse> {
  const response = await fetch(`${API_BASE_URL}/api/score-weights`)
  if (!response.ok) throw new Error('Failed to fetch score weights')
  return response.json()
}

export async function updateScoreWeights(
  weights: Record<string, number>,
  token?: string,
): Promise<ScoreWeightsResponse> {
  const response = await fetch(`${API_BASE_URL}/api/score-weights`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ weights }),
  })
  if (!response.ok) throw new Error('Failed to update score weights')
  return response.json()
}

export async function getRateLimits(token?: string): Promise<Record<string, { remaining: number; limit: number }>> {
  const response = await fetch(`${API_BASE_URL}/api/rate-limits`, {
    headers: authHeaders(token),
  })
  if (!response.ok) throw new Error('Failed to fetch rate limits')
  return response.json()
}

export async function refreshAllScores(
  force = false,
  concurrency = 3,
  token?: string,
): Promise<{ status: string; message: string }> {
  const response = await fetch(
    `${API_BASE_URL}/api/ratings/refresh-all?force=${force}&concurrency=${concurrency}`,
    { method: 'POST', headers: authHeaders(token) },
  )
  if (!response.ok) throw new Error('Failed to start refresh')
  return response.json()
}

export async function recalculateScores(token?: string): Promise<{ recalculated: number }> {
  const response = await fetch(`${API_BASE_URL}/api/score-weights/recalculate`, {
    method: 'POST',
    headers: authHeaders(token),
  })
  if (!response.ok) throw new Error('Failed to recalculate scores')
  return response.json()
}

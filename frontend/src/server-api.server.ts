const INTERNAL_API_BASE_URL = (
  process.env.INTERNAL_API_BASE_URL
  ?? process.env.VITE_API_BASE_URL
  ?? 'http://127.0.0.1:8000'
).replace(/\/$/, '')

export class BackendResponseError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'BackendResponseError'
    this.status = status
  }
}

const DEFAULT_RETRY_AFTER_SECONDS = '30'

// A rate-limited or struggling backend is a temporary condition, not a server
// bug: answer 429/503 with Retry-After so crawlers and CDNs back off instead of
// recording a 500.
export function temporaryFailureResponse(status: number, retryAfter?: string | null): Response {
  const rateLimited = status === 429
  return new Response(rateLimited ? 'Too Many Requests' : 'Service Unavailable', {
    status: rateLimited ? 429 : 503,
    headers: {
      'Retry-After': retryAfter && /^\d{1,5}$/.test(retryAfter) ? retryAfter : DEFAULT_RETRY_AFTER_SECONDS,
      'Cache-Control': 'no-store',
    },
  })
}

// nginx overwrites X-Forwarded-For with the real peer, so it is safe to pass on.
// Without it every server-side render shares the frontend container's address
// and therefore one rate-limit bucket at the backend.
export function clientForwardHeaders(request: Request): HeadersInit {
  const forwarded = request.headers.get('x-forwarded-for')
  return forwarded ? { 'X-Forwarded-For': forwarded } : {}
}

export async function fetchBackend<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${INTERNAL_API_BASE_URL}${path}`, {
      ...init,
      signal: init?.signal ?? AbortSignal.timeout(10_000),
      headers: {
        Accept: 'application/json',
        ...init?.headers,
      },
    })
  } catch (error) {
    if (init?.signal?.aborted) throw error
    throw temporaryFailureResponse(503)
  }
  if (response.status === 429 || response.status >= 500) {
    throw temporaryFailureResponse(response.status, response.headers.get('Retry-After'))
  }
  if (!response.ok) {
    throw new BackendResponseError(response.status, `Backend returned ${response.status}`)
  }
  return response.json() as Promise<T>
}

export interface RankingGenre {
  slug: string
  name: string
}

const RELATED_GENRE_LIMIT = 8

/**
 * Most populated genre landing pages, for internal links. Links are decoration,
 * so any failure (including a rate limit) just yields none instead of failing
 * the page that asked.
 */
export async function loadTopGenres(init?: RequestInit): Promise<RankingGenre[]> {
  try {
    const { genres } = await fetchBackend<{ genres: Array<RankingGenre & { count: number }> }>(
      '/api/seo/genres',
      init,
    )
    return genres.slice(0, RELATED_GENRE_LIMIT).map(({ slug, name }) => ({ slug, name }))
  } catch {
    return []
  }
}

import { API_BASE_URL } from './api'

export interface AdminTokenResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
}

export interface AdminApiHealth {
  [source: string]: {
    configured: boolean
    working: boolean
    status: string
    message?: string
    latency_ms?: number
  }
}

export interface AdminDashboard {
  catalog: {
    total_games: number
    rankable_games: number
    non_game_rows: number
    rating_snapshots: number
    source_snapshots: number
  }
  traffic: {
    days: number
    total_visits: number
    unique_visitors: number
    visits_today: number
    unique_today: number
    top_pages: Array<{ path: string; visits: number }>
    daily: Array<{ date: string; visits: number; visitors: number }>
    recent_visits: Array<{
      path: string
      created_at: string
      visitor: string
      referrer?: string | null
      screen?: string | null
    }>
  }
}

export interface DataFillRun {
  id: number
  status: string
  force: boolean
  target_total: number
  result: Record<string, unknown>
  error?: string | null
  started_at: string
  finished_at?: string | null
}

export interface DataFillStatus {
  running: boolean
  catalog: {
    total_games: number
    missing_ratings: number
    missing_metadata: number
    missing_hltb: number
    missing_prices: number
    missing_external_ids: number
  }
  rate_limits: Record<string, { remaining: number; limit: number }>
  last_run?: DataFillRun | null
}

export class AdminApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'AdminApiError'
    this.status = status
  }
}

function adminHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}

async function parseError(response: Response): Promise<AdminApiError> {
  try {
    const body: unknown = await response.json()
    if (typeof body === 'object' && body !== null && 'detail' in body && typeof body.detail === 'string') {
      return new AdminApiError(body.detail, response.status)
    }
  } catch {
    // Keep the status fallback.
  }
  return new AdminApiError(`Request failed with ${response.status}`, response.status)
}

export async function loginAdmin(username: string, password: string): Promise<AdminTokenResponse> {
  const body = new URLSearchParams()
  body.set('username', username)
  body.set('password', password)

  const response = await fetch(`${API_BASE_URL}/api/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  })
  if (!response.ok) throw await parseError(response)
  return response.json()
}

export async function getAdminDashboard(token: string, days = 7): Promise<AdminDashboard> {
  const response = await fetch(`${API_BASE_URL}/admin/dashboard?days=${days}`, {
    headers: adminHeaders(token),
  })
  if (!response.ok) throw await parseError(response)
  return response.json()
}

export async function getAdminApiHealth(token: string): Promise<AdminApiHealth> {
  const response = await fetch(`${API_BASE_URL}/admin/api-health`, {
    headers: adminHeaders(token),
  })
  if (!response.ok) throw await parseError(response)
  return response.json()
}

export async function getDataFillStatus(token: string): Promise<DataFillStatus> {
  const response = await fetch(`${API_BASE_URL}/admin/data-fill/status`, {
    headers: adminHeaders(token),
  })
  if (!response.ok) throw await parseError(response)
  return response.json()
}

export async function runDataFill(
  token: string,
  options: { force?: boolean; targetTotal?: number } = {},
): Promise<{ status: string; run: DataFillRun }> {
  const params = new URLSearchParams()
  if (options.force) params.set('force', 'true')
  if (options.targetTotal) params.set('target_total', String(options.targetTotal))
  const query = params.toString()
  const response = await fetch(`${API_BASE_URL}/admin/data-fill/run${query ? `?${query}` : ''}`, {
    method: 'POST',
    headers: adminHeaders(token),
  })
  if (!response.ok) throw await parseError(response)
  return response.json()
}

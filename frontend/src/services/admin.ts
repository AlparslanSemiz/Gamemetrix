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

function adminHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}

async function parseError(response: Response): Promise<Error> {
  try {
    const body = await response.json()
    if (typeof body?.detail === 'string') return new Error(body.detail)
  } catch {
    // Keep the status fallback.
  }
  return new Error(`Request failed with ${response.status}`)
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

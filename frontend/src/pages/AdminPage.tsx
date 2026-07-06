import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  Activity,
  Database,
  Eye,
  KeyRound,
  LogOut,
  RefreshCw,
  Server,
  ShieldCheck,
  Users,
} from 'lucide-react'
import {
  getAdminApiHealth,
  getAdminDashboard,
  loginAdmin,
  type AdminApiHealth,
  type AdminDashboard,
} from '../services/admin'
import './AdminPage.css'

const ADMIN_TOKEN_KEY = 'gamemetrix.adminToken.v1'

function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-US').format(value)
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat('tr-TR', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function healthClass(status: AdminApiHealth[string]): string {
  if (!status.configured) return 'is-muted'
  return status.working ? 'is-ok' : 'is-bad'
}

export function AdminPage() {
  const [token, setToken] = useState(() => window.localStorage.getItem(ADMIN_TOKEN_KEY) ?? '')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [dashboard, setDashboard] = useState<AdminDashboard | null>(null)
  const [health, setHealth] = useState<AdminApiHealth>({})
  const [isLoading, setIsLoading] = useState(false)
  const [isSigningIn, setIsSigningIn] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadDashboard = useCallback(async () => {
    if (!token) return
    setIsLoading(true)
    setError(null)
    try {
      const [dashboardResponse, healthResponse] = await Promise.all([
        getAdminDashboard(token),
        getAdminApiHealth(token),
      ])
      setDashboard(dashboardResponse)
      setHealth(healthResponse)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Admin dashboard could not be loaded.')
    } finally {
      setIsLoading(false)
    }
  }, [token])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadDashboard()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [loadDashboard])

  const maxDailyVisits = useMemo(() => {
    const visits = dashboard?.traffic.daily.map((row) => row.visits) ?? []
    return Math.max(1, ...visits)
  }, [dashboard])

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSigningIn(true)
    setError(null)
    try {
      const response = await loginAdmin(username.trim(), password)
      window.localStorage.setItem(ADMIN_TOKEN_KEY, response.access_token)
      setToken(response.access_token)
      setPassword('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed.')
    } finally {
      setIsSigningIn(false)
    }
  }

  function handleLogout() {
    window.localStorage.removeItem(ADMIN_TOKEN_KEY)
    setToken('')
    setDashboard(null)
    setHealth({})
  }

  if (!token) {
    return (
      <main className="admin-shell">
        <section className="admin-login-panel">
          <div className="admin-login-mark">
            <ShieldCheck size={24} aria-hidden="true" />
          </div>
          <h1>GameMetrix Admin</h1>
          <form className="admin-login-form" onSubmit={handleLogin}>
            <label>
              <span>Username</span>
              <input
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
              />
            </label>
            <label>
              <span>Password</span>
              <input
                autoComplete="current-password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <button type="submit" disabled={isSigningIn}>
              <KeyRound size={16} aria-hidden="true" />
              <span>{isSigningIn ? 'Signing in' : 'Sign in'}</span>
            </button>
          </form>
          {error ? <p className="admin-error">{error}</p> : null}
        </section>
      </main>
    )
  }

  return (
    <main className="admin-shell">
      <header className="admin-header">
        <div>
          <span className="admin-kicker">Admin</span>
          <h1>GameMetrix Dashboard</h1>
        </div>
        <div className="admin-header-actions">
          <button type="button" onClick={loadDashboard} disabled={isLoading}>
            <RefreshCw size={16} aria-hidden="true" />
            <span>{isLoading ? 'Refreshing' : 'Refresh'}</span>
          </button>
          <button type="button" onClick={handleLogout}>
            <LogOut size={16} aria-hidden="true" />
            <span>Logout</span>
          </button>
        </div>
      </header>

      {error ? <p className="admin-error">{error}</p> : null}

      <section className="admin-metric-grid" aria-label="Key metrics">
        <article className="admin-metric">
          <Database size={18} aria-hidden="true" />
          <span>Total games</span>
          <strong>{formatNumber(dashboard?.catalog.total_games ?? 0)}</strong>
        </article>
        <article className="admin-metric">
          <ShieldCheck size={18} aria-hidden="true" />
          <span>Rankable</span>
          <strong>{formatNumber(dashboard?.catalog.rankable_games ?? 0)}</strong>
        </article>
        <article className="admin-metric">
          <Eye size={18} aria-hidden="true" />
          <span>Visits today</span>
          <strong>{formatNumber(dashboard?.traffic.visits_today ?? 0)}</strong>
        </article>
        <article className="admin-metric">
          <Users size={18} aria-hidden="true" />
          <span>Unique today</span>
          <strong>{formatNumber(dashboard?.traffic.unique_today ?? 0)}</strong>
        </article>
      </section>

      <section className="admin-grid">
        <article className="admin-panel admin-panel-wide">
          <div className="admin-panel-head">
            <h2>Traffic</h2>
            <span>{dashboard?.traffic.days ?? 7} days</span>
          </div>
          <div className="admin-traffic-bars">
            {dashboard?.traffic.daily.map((row) => (
              <div className="admin-traffic-day" key={row.date}>
                <div className="admin-bar-track">
                  <span style={{ height: `${Math.max(6, (row.visits / maxDailyVisits) * 100)}%` }} />
                </div>
                <strong>{row.visits}</strong>
                <small>{row.date.slice(5)}</small>
              </div>
            ))}
          </div>
          <div className="admin-inline-stats">
            <span>{formatNumber(dashboard?.traffic.total_visits ?? 0)} visits</span>
            <span>{formatNumber(dashboard?.traffic.unique_visitors ?? 0)} visitors</span>
          </div>
        </article>

        <article className="admin-panel">
          <div className="admin-panel-head">
            <h2>Top Pages</h2>
          </div>
          <div className="admin-row-list">
            {dashboard?.traffic.top_pages.length ? dashboard.traffic.top_pages.map((page) => (
              <div className="admin-row" key={page.path}>
                <span title={page.path}>{page.path}</span>
                <strong>{formatNumber(page.visits)}</strong>
              </div>
            )) : <p className="admin-empty">No visits yet.</p>}
          </div>
        </article>

        <article className="admin-panel">
          <div className="admin-panel-head">
            <h2>API Health</h2>
          </div>
          <div className="admin-health-list">
            {Object.entries(health).map(([source, status]) => (
              <div className="admin-health-row" key={source}>
                <span className={`admin-dot ${healthClass(status)}`} />
                <div>
                  <strong>{source}</strong>
                  <small>{status.configured ? status.status : 'not configured'}</small>
                </div>
                {status.latency_ms ? <em>{Math.round(status.latency_ms)}ms</em> : null}
              </div>
            ))}
          </div>
        </article>

        <article className="admin-panel">
          <div className="admin-panel-head">
            <h2>Catalog</h2>
            <Server size={16} aria-hidden="true" />
          </div>
          <div className="admin-row-list">
            <div className="admin-row">
              <span>Non-game rows</span>
              <strong>{formatNumber(dashboard?.catalog.non_game_rows ?? 0)}</strong>
            </div>
            <div className="admin-row">
              <span>Rating snapshots</span>
              <strong>{formatNumber(dashboard?.catalog.rating_snapshots ?? 0)}</strong>
            </div>
            <div className="admin-row">
              <span>Source snapshots</span>
              <strong>{formatNumber(dashboard?.catalog.source_snapshots ?? 0)}</strong>
            </div>
          </div>
        </article>

        <article className="admin-panel admin-panel-wide">
          <div className="admin-panel-head">
            <h2>Recent Visits</h2>
            <Activity size={16} aria-hidden="true" />
          </div>
          <div className="admin-visit-table">
            {dashboard?.traffic.recent_visits.length ? dashboard.traffic.recent_visits.map((visit) => (
              <div className="admin-visit-row" key={`${visit.created_at}-${visit.visitor}-${visit.path}`}>
                <span>{formatDateTime(visit.created_at)}</span>
                <strong title={visit.path}>{visit.path}</strong>
                <em>{visit.visitor}</em>
                <small>{visit.screen ?? 'unknown'}</small>
              </div>
            )) : <p className="admin-empty">No visits recorded.</p>}
          </div>
        </article>
      </section>
    </main>
  )
}

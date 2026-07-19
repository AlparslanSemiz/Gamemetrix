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
  AdminApiError,
  getAdminApiHealth,
  getAdminDashboard,
  getDataFillStatus,
  loginAdmin,
  runDataFill,
  type AdminApiHealth,
  type AdminDashboard,
  type DataFillStatus,
} from '../services/admin'
import { RefreshAllPanel } from '../components/RefreshAllPanel'
import { ScoreWeightSettings } from '../components/ScoreWeightSettings'
import './AdminPage.css'

const ADMIN_TOKEN_KEY = 'gamemetrix.adminToken.v1'
const ADMIN_TOKEN_STORAGE = window.sessionStorage
const ADMIN_USERNAME_MAX_LENGTH = 64
const ADMIN_PASSWORD_MAX_LENGTH = 128
const TRAFFIC_DAY_OPTIONS = [7, 14, 30] as const
// Past this range, per-bar labels no longer fit — the chart switches to tooltips only.
const DENSE_TRAFFIC_THRESHOLD = 10

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
  const [token, setToken] = useState(() => ADMIN_TOKEN_STORAGE.getItem(ADMIN_TOKEN_KEY) ?? '')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [dashboard, setDashboard] = useState<AdminDashboard | null>(null)
  const [health, setHealth] = useState<AdminApiHealth>({})
  const [dataFill, setDataFill] = useState<DataFillStatus | null>(null)
  const [trafficDays, setTrafficDays] = useState<number>(TRAFFIC_DAY_OPTIONS[0])
  const [isLoading, setIsLoading] = useState(false)
  const [isSigningIn, setIsSigningIn] = useState(false)
  const [isStartingDataFill, setIsStartingDataFill] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadDashboard = useCallback(async () => {
    if (!token) return
    setIsLoading(true)
    setError(null)
    try {
      const [dashboardResponse, healthResponse, dataFillResponse] = await Promise.all([
        getAdminDashboard(token, trafficDays),
        getAdminApiHealth(token),
        getDataFillStatus(token),
      ])
      setDashboard(dashboardResponse)
      setHealth(healthResponse)
      setDataFill(dataFillResponse)
    } catch (err) {
      if (err instanceof AdminApiError && err.status === 401) {
        ADMIN_TOKEN_STORAGE.removeItem(ADMIN_TOKEN_KEY)
        setToken('')
        setDashboard(null)
        setHealth({})
        setDataFill(null)
        setError('Session expired. Please sign in again.')
        return
      }
      setError(err instanceof Error ? err.message : 'Admin dashboard could not be loaded.')
    } finally {
      setIsLoading(false)
    }
  }, [token, trafficDays])

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

  const dataGaps = useMemo(() => {
    const catalog = dataFill?.catalog
    return [
      ['Missing ratings', catalog?.missing_ratings ?? 0],
      ['Missing metadata', catalog?.missing_metadata ?? 0],
      ['Missing HLTB', catalog?.missing_hltb ?? 0],
      ['Missing prices', catalog?.missing_prices ?? 0],
      ['Missing external IDs', catalog?.missing_external_ids ?? 0],
    ] as const
  }, [dataFill])

  const rateLimitRows = useMemo(() => {
    return Object.entries(dataFill?.rate_limits ?? {})
      .filter(([source]) => ['RAWG', 'IGDB', 'Steam', 'SteamSpy', 'CheapShark', 'FreeToGame', 'ITAD', 'OpenCritic'].includes(source))
      .sort(([a], [b]) => a.localeCompare(b))
  }, [dataFill])

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSigningIn(true)
    setError(null)
    try {
      const response = await loginAdmin(username.trim(), password)
      ADMIN_TOKEN_STORAGE.setItem(ADMIN_TOKEN_KEY, response.access_token)
      setToken(response.access_token)
      setPassword('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed.')
    } finally {
      setIsSigningIn(false)
    }
  }

  function handleLogout() {
    ADMIN_TOKEN_STORAGE.removeItem(ADMIN_TOKEN_KEY)
    setToken('')
    setDashboard(null)
    setHealth({})
    setDataFill(null)
  }

  async function handleStartDataFill() {
    if (!token) return
    setIsStartingDataFill(true)
    setError(null)
    try {
      await runDataFill(token, { targetTotal: 10000 })
      setDataFill(await getDataFillStatus(token))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Data fill could not be started.')
    } finally {
      setIsStartingDataFill(false)
    }
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
                required
                maxLength={ADMIN_USERNAME_MAX_LENGTH}
                value={username}
                onChange={(event) => setUsername(event.target.value)}
              />
            </label>
            <label>
              <span>Password</span>
              <input
                autoComplete="current-password"
                type="password"
                required
                maxLength={ADMIN_PASSWORD_MAX_LENGTH}
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
            <div className="admin-day-picker" role="group" aria-label="Traffic range">
              {TRAFFIC_DAY_OPTIONS.map((option) => (
                <button
                  key={option}
                  type="button"
                  className={option === trafficDays ? 'is-active' : ''}
                  onClick={() => setTrafficDays(option)}
                  disabled={isLoading}
                >
                  {option}d
                </button>
              ))}
            </div>
          </div>
          <div
            className={`admin-traffic-bars${trafficDays > DENSE_TRAFFIC_THRESHOLD ? ' admin-traffic-dense' : ''}`}
            style={{ gridTemplateColumns: `repeat(${dashboard?.traffic.daily.length ?? trafficDays}, minmax(0, 1fr))` }}
          >
            {dashboard?.traffic.daily.map((row) => (
              <div className="admin-traffic-day" key={row.date} title={`${row.date}: ${row.visits} visits, ${row.visitors} visitors`}>
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

        <article className="admin-panel admin-panel-wide">
          <div className="admin-panel-head">
            <h2>Data Fill</h2>
            <button type="button" onClick={handleStartDataFill} disabled={isStartingDataFill || dataFill?.running}>
              <RefreshCw size={15} aria-hidden="true" />
              <span>{isStartingDataFill ? 'Starting' : dataFill?.running ? 'Running' : 'Run fill'}</span>
            </button>
          </div>
          <div className="admin-data-fill-grid">
            <div className="admin-row-list">
              <div className="admin-row">
                <span>Total games</span>
                <strong>{formatNumber(dataFill?.catalog.total_games ?? 0)}</strong>
              </div>
              {dataGaps.map(([label, value]) => (
                <div className="admin-row" key={label}>
                  <span>{label}</span>
                  <strong>{formatNumber(value)}</strong>
                </div>
              ))}
            </div>
            <div className="admin-budget-list">
              {rateLimitRows.map(([source, budget]) => {
                const pct = budget.limit > 0 ? (budget.remaining / budget.limit) * 100 : 0
                return (
                  <div className="admin-budget-row" key={source}>
                    <span>{source}</span>
                    <div className="admin-budget-track">
                      <i style={{ width: `${Math.max(4, pct)}%` }} />
                    </div>
                    <strong>{budget.remaining}/{budget.limit}</strong>
                  </div>
                )
              })}
            </div>
          </div>
          <div className="admin-inline-stats">
            <span>Last run: {dataFill?.last_run ? dataFill.last_run.status : 'none'}</span>
            {dataFill?.last_run?.finished_at ? <span>{formatDateTime(dataFill.last_run.finished_at)}</span> : null}
          </div>
        </article>

        <article className="admin-panel admin-panel-wide">
          <div className="admin-panel-head">
            <h2>Score Weights</h2>
          </div>
          <ScoreWeightSettings token={token} onSaved={() => { void loadDashboard() }} />
        </article>

        <article className="admin-panel">
          <div className="admin-panel-head">
            <h2>Score Data</h2>
          </div>
          <RefreshAllPanel token={token} />
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

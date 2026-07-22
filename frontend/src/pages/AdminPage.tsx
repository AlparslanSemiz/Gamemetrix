import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  Activity,
  Database,
  Eye,
  KeyRound,
  LogOut,
  RefreshCw,
  ScrollText,
  Server,
  ShieldCheck,
  Users,
} from 'lucide-react'
import {
  AdminApiError,
  getAdminApiHealth,
  getAdminAuditLogs,
  getAdminDashboard,
  getDataFillStatus,
  loginAdmin,
  runDataFill,
  runPrimaryScores,
  type AdminApiHealth,
  type AdminAuditLog,
  type AdminDashboard,
  type DataFillStatus,
} from '../services/admin'
import { RefreshAllPanel } from '../components/RefreshAllPanel'
import { ScoreWeightSettings } from '../components/ScoreWeightSettings'
import './AdminPage.css'

const ADMIN_USERNAME_MAX_LENGTH = 64
const ADMIN_PASSWORD_MAX_LENGTH = 128
const AUDIT_LOG_LIMIT = 100

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
  // Keep the bearer token in component memory only. A reload deliberately
  // requires a fresh admin login so an XSS cannot recover a token at rest.
  const [token, setToken] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [dashboard, setDashboard] = useState<AdminDashboard | null>(null)
  const [health, setHealth] = useState<AdminApiHealth>({})
  const [dataFill, setDataFill] = useState<DataFillStatus | null>(null)
  const [auditLogs, setAuditLogs] = useState<AdminAuditLog[]>([])
  const [auditOnlyFailures, setAuditOnlyFailures] = useState(false)
  const [trafficDays, setTrafficDays] = useState<number>(TRAFFIC_DAY_OPTIONS[0])
  const [isLoading, setIsLoading] = useState(false)
  const [isSigningIn, setIsSigningIn] = useState(false)
  const [isStartingDataFill, setIsStartingDataFill] = useState(false)
  const [isStartingPrimaryScores, setIsStartingPrimaryScores] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const signOutExpiredSession = useCallback(() => {
    setToken('')
    setDashboard(null)
    setHealth({})
    setDataFill(null)
    setAuditLogs([])
    setError('Session expired. Please sign in again.')
  }, [])

  const loadDashboard = useCallback(async () => {
    if (!token) return
    setIsLoading(true)
    setError(null)

    // allSettled, not all: these four panels are independent, and a single
    // failing endpoint (a pending migration, a slow provider health check) must
    // not blank the entire dashboard.
    const [dashboardResult, healthResult, dataFillResult, auditResult] = await Promise.allSettled([
      getAdminDashboard(token, trafficDays),
      getAdminApiHealth(token),
      getDataFillStatus(token),
      getAdminAuditLogs(token, { limit: AUDIT_LOG_LIMIT, onlyFailures: auditOnlyFailures }),
    ])
    setIsLoading(false)

    const results = [dashboardResult, healthResult, dataFillResult, auditResult]
    if (results.some((r) => r.status === 'rejected' && r.reason instanceof AdminApiError && r.reason.status === 401)) {
      signOutExpiredSession()
      return
    }

    if (dashboardResult.status === 'fulfilled') setDashboard(dashboardResult.value)
    if (healthResult.status === 'fulfilled') setHealth(healthResult.value)
    if (dataFillResult.status === 'fulfilled') setDataFill(dataFillResult.value)
    if (auditResult.status === 'fulfilled') setAuditLogs(auditResult.value)

    const failures = [
      ['Dashboard', dashboardResult],
      ['API health', healthResult],
      ['Data fill', dataFillResult],
      ['Audit log', auditResult],
    ] as const
    const messages = failures
      .filter(([, result]) => result.status === 'rejected')
      .map(([label, result]) => {
        const reason = (result as PromiseRejectedResult).reason
        return `${label}: ${reason instanceof Error ? reason.message : 'request failed'}`
      })
    setError(messages.length ? messages.join(' · ') : null)
  }, [token, trafficDays, auditOnlyFailures, signOutExpiredSession])

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
      ['Missing 4-source score slots', catalog?.missing_primary_scores ?? 0],
      ['Missing metadata', catalog?.missing_metadata ?? 0],
      ['Missing HLTB', catalog?.missing_hltb ?? 0],
      ['Missing prices', catalog?.missing_prices ?? 0],
      ['Missing external IDs', catalog?.missing_external_ids ?? 0],
    ] as const
  }, [dataFill])

  const rateLimitRows = useMemo(() => {
    return Object.entries(dataFill?.rate_limits ?? {})
      .filter(([source]) => ['Metacritic', 'RAWG', 'IGDB', 'Steam', 'SteamSpy', 'CheapShark', 'FreeToGame', 'ITAD', 'OpenCritic'].includes(source))
      .sort(([a], [b]) => a.localeCompare(b))
  }, [dataFill])

  const primaryScoreRows = useMemo(() => {
    return Object.entries(dataFill?.primary_scores.sources ?? {})
      .sort(([a], [b]) => a.localeCompare(b))
  }, [dataFill])

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSigningIn(true)
    setError(null)
    try {
      const response = await loginAdmin(username.trim(), password)
      setToken(response.access_token)
      setPassword('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed.')
    } finally {
      setIsSigningIn(false)
    }
  }

  function handleLogout() {
    setToken('')
    setDashboard(null)
    setHealth({})
    setDataFill(null)
    setAuditLogs([])
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

  async function handleStartPrimaryScores() {
    if (!token) return
    setIsStartingPrimaryScores(true)
    setError(null)
    try {
      await runPrimaryScores(token, { limit: 10000 })
      setDataFill(await getDataFillStatus(token))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Primary scores could not be started.')
    } finally {
      setIsStartingPrimaryScores(false)
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
          <Users size={18} aria-hidden="true" />
          <span>Visitors all time</span>
          <strong>{formatNumber(dashboard?.traffic.total_unique_visitors ?? 0)}</strong>
        </article>
        <article className="admin-metric">
          <ShieldCheck size={18} aria-hidden="true" />
          <span>Unique IPs all time</span>
          <strong>{formatNumber(dashboard?.traffic.total_unique_ips ?? 0)}</strong>
        </article>
        <article className="admin-metric">
          <Eye size={18} aria-hidden="true" />
          <span>Visits today</span>
          <strong>{formatNumber(dashboard?.traffic.visits_today ?? 0)}</strong>
        </article>
        <article className="admin-metric">
          <Users size={18} aria-hidden="true" />
          <span>Registered accounts</span>
          <strong>{formatNumber(dashboard?.accounts.registered ?? 0)}</strong>
        </article>
        <article className="admin-metric">
          <Database size={18} aria-hidden="true" />
          <span>SEO pages ready</span>
          <strong>{formatNumber(dashboard?.catalog.seo_indexable_games ?? 0)}</strong>
        </article>
        <article className="admin-metric">
          <Eye size={18} aria-hidden="true" />
          <span>Google sessions</span>
          <strong>{formatNumber(dashboard?.acquisition.organic_sessions ?? 0)}</strong>
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
            <span>{formatNumber(dashboard?.traffic.unique_ips ?? 0)} IPs</span>
            <span>{formatNumber(dashboard?.traffic.unique_today ?? 0)} unique today</span>
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
                  <small title={status.message}>{status.message ?? (status.configured ? status.status : 'not configured')}</small>
                </div>
                {status.latency_ms ? <em>{Math.round(status.latency_ms)}ms</em> : null}
              </div>
            ))}
          </div>
        </article>

        <article className="admin-panel">
          <div className="admin-panel-head"><h2>Accounts</h2></div>
          <div className="admin-row-list">
            <div className="admin-row"><span>Registered</span><strong>{formatNumber(dashboard?.accounts.registered ?? 0)}</strong></div>
            <div className="admin-row"><span>Verified</span><strong>{formatNumber(dashboard?.accounts.verified ?? 0)}</strong></div>
            <div className="admin-row"><span>Active in 30 days</span><strong>{formatNumber(dashboard?.accounts.active_30d ?? 0)}</strong></div>
            <div className="admin-row"><span>Signup conversion</span><strong>{(dashboard?.acquisition.signup_conversion ?? 0).toFixed(2)}%</strong></div>
            <div className="admin-row"><span>Store outbound</span><strong>{formatNumber(dashboard?.acquisition.outbound_store_clicks ?? 0)}</strong></div>
            {Object.entries(dashboard?.acquisition.events ?? {}).map(([event, count]) => (
              <div className="admin-row" key={event}><span>{event.replaceAll('_', ' ')}</span><strong>{formatNumber(count)}</strong></div>
            ))}
          </div>
        </article>

        <article className="admin-panel">
          <div className="admin-panel-head"><h2>Organic Landing Pages</h2></div>
          <div className="admin-row-list">
            {dashboard?.acquisition.organic_landing_pages.length ? dashboard.acquisition.organic_landing_pages.map((page) => (
              <div className="admin-row" key={page.path}><span title={page.path}>{page.path}</span><strong>{formatNumber(page.visits)}</strong></div>
            )) : <p className="admin-empty">No Google referrals in this range.</p>}
            <div className="admin-row"><span>Repeat visitors</span><strong>{formatNumber(dashboard?.acquisition.repeat_visitors ?? 0)}</strong></div>
            <div className="admin-row"><span>Google visitors</span><strong>{formatNumber(dashboard?.acquisition.organic_visitors ?? 0)}</strong></div>
            <div className="admin-row"><span>Google signups</span><strong>{formatNumber(dashboard?.acquisition.organic_signups ?? 0)}</strong></div>
            <div className="admin-row"><span>Google conversion</span><strong>{(dashboard?.acquisition.organic_signup_conversion ?? 0).toFixed(2)}%</strong></div>
          </div>
        </article>

        <article className="admin-panel">
          <div className="admin-panel-head"><h2>SEO Exclusions</h2></div>
          <div className="admin-row-list">
            {Object.entries(dashboard?.catalog.seo_exclusions ?? {}).sort(([, left], [, right]) => right - left).map(([reason, count]) => (
              <div className="admin-row" key={reason}><span>{reason.replaceAll('_', ' ')}</span><strong>{formatNumber(count)}</strong></div>
            ))}
          </div>
        </article>

        <article className="admin-panel admin-panel-wide">
          <div className="admin-panel-head">
            <h2>Data Fill</h2>
            <div className="admin-panel-actions">
              <button type="button" onClick={handleStartPrimaryScores} disabled={isStartingPrimaryScores || dataFill?.running}>
                <RefreshCw size={15} aria-hidden="true" />
                <span>{isStartingPrimaryScores ? 'Starting' : dataFill?.running ? 'Running' : 'Fill 4 scores'}</span>
              </button>
              <button type="button" onClick={handleStartDataFill} disabled={isStartingDataFill || dataFill?.running}>
                <RefreshCw size={15} aria-hidden="true" />
                <span>{isStartingDataFill ? 'Starting' : dataFill?.running ? 'Running' : 'Run fill'}</span>
              </button>
            </div>
          </div>
          <div className="admin-data-fill-grid">
            <div className="admin-row-list">
              <div className="admin-row">
                <span>Total games</span>
                <strong>{formatNumber(dataFill?.catalog.total_games ?? 0)}</strong>
              </div>
              <div className="admin-row">
                <span>4-source complete</span>
                <strong>
                  {formatNumber(dataFill?.primary_scores.complete_games ?? 0)}
                  /
                  {formatNumber(dataFill?.primary_scores.total_games ?? 0)}
                </strong>
              </div>
              {dataGaps.map(([label, value]) => (
                <div className="admin-row" key={label}>
                  <span>{label}</span>
                  <strong>{formatNumber(value)}</strong>
                </div>
              ))}
            </div>
            <div className="admin-budget-list">
              {primaryScoreRows.map(([source, coverage]) => (
                <div className="admin-row" key={`coverage-${source}`}>
                  <span>{source} live</span>
                  <strong>
                    {formatNumber(coverage.live)}
                    /
                    {formatNumber(dataFill?.primary_scores.total_games ?? 0)}
                  </strong>
                </div>
              ))}
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
              <div className="admin-visit-row" key={`${visit.created_at}-${visit.visitor}-${visit.path}`} title={visit.user_agent ?? visit.referrer ?? undefined}>
                <span>{formatDateTime(visit.created_at)}</span>
                <strong title={visit.path}>{visit.path}</strong>
                <em>{visit.ip ?? `#${visit.ip_fingerprint ?? 'unknown'}`}</em>
                <small title={visit.account ?? undefined}>
                  {visit.account ?? visit.country ?? visit.timezone ?? visit.language ?? visit.screen ?? 'anonymous'}
                </small>
              </div>
            )) : <p className="admin-empty">No visits recorded.</p>}
          </div>
        </article>

        <article className="admin-panel admin-panel-full">
          <div className="admin-panel-head">
            <h2>Visitor IPs</h2>
            <span>
              {dashboard?.traffic.tracking.raw_ip_enabled
                ? `${dashboard.traffic.tracking.raw_ip_retention_days}d raw retention`
                : 'Raw IP storage disabled'}
            </span>
          </div>
          <div className="admin-ip-table">
            {dashboard?.traffic.recent_ips.length ? dashboard.traffic.recent_ips.map((entry) => (
              <div className="admin-ip-row" key={entry.fingerprint}>
                <strong>{entry.ip ?? `#${entry.fingerprint}`}</strong>
                <span>{entry.country ?? 'unknown'}</span>
                <em>{formatNumber(entry.visits)} visits</em>
                <small>{formatDateTime(entry.first_seen)}</small>
                <small>{formatDateTime(entry.last_seen)}</small>
              </div>
            )) : <p className="admin-empty">No visitor IPs recorded.</p>}
          </div>
        </article>

        <article className="admin-panel admin-panel-full">
          <div className="admin-panel-head">
            <h2>Admin Activity</h2>
            <button
              type="button"
              className={auditOnlyFailures ? 'admin-audit-filter is-active' : 'admin-audit-filter'}
              onClick={() => setAuditOnlyFailures((previous) => !previous)}
            >
              <ScrollText size={14} aria-hidden="true" />
              <span>{auditOnlyFailures ? 'Failures only' : 'All requests'}</span>
            </button>
          </div>
          <div className="admin-audit-table">
            {auditLogs.length ? auditLogs.map((entry) => (
              <div
                className={entry.success ? 'admin-audit-row' : 'admin-audit-row is-failure'}
                key={entry.id}
                title={entry.user_agent ?? undefined}
              >
                <span>{formatDateTime(entry.created_at)}</span>
                <strong>{entry.username ?? 'anonymous'}</strong>
                <em>{entry.action === 'login' ? 'login' : entry.method}</em>
                <small title={entry.query ? `${entry.path}?${entry.query}` : entry.path}>
                  {entry.path}
                </small>
                <span className="admin-audit-status">{entry.status_code}</span>
                <small>{entry.ip_address ?? 'unknown'}</small>
              </div>
            )) : <p className="admin-empty">No admin activity recorded.</p>}
          </div>
        </article>
      </section>
    </main>
  )
}

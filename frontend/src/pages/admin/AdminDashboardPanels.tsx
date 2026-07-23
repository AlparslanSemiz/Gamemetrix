import {
  Activity,
  Database,
  Eye,
  RefreshCw,
  ScrollText,
  Server,
  ShieldCheck,
  Users,
} from 'lucide-react'
import { RefreshAllPanel } from '../../components/RefreshAllPanel'
import { ScoreWeightSettings } from '../../components/ScoreWeightSettings'
import type {
  AdminApiHealth,
  AdminAuditLog,
  AdminDashboard,
  DataFillStatus,
  PrimaryScoreCoverage,
} from '../../services/admin'
import {
  adminHealthClass,
  formatAdminDateTime,
  formatAdminNumber,
} from './format'
import { TRAFFIC_DAY_OPTIONS } from './useAdminDashboard'

const DENSE_TRAFFIC_THRESHOLD = 10
const MINIMUM_TRAFFIC_BAR_PERCENT = 6
const MINIMUM_BUDGET_BAR_PERCENT = 4

export function AdminMetrics({
  dashboard,
}: {
  dashboard: AdminDashboard | null
}) {
  const metrics = [
    [Database, 'Total games', dashboard?.catalog.total_games ?? 0],
    [Users, 'Visitors all time', dashboard?.traffic.total_unique_visitors ?? 0],
    [ShieldCheck, 'Unique IPs all time', dashboard?.traffic.total_unique_ips ?? 0],
    [Eye, 'Visits today', dashboard?.traffic.visits_today ?? 0],
    [Users, 'Registered accounts', dashboard?.accounts.registered ?? 0],
    [Database, 'SEO pages ready', dashboard?.catalog.seo_indexable_games ?? 0],
    [Eye, 'Google sessions', dashboard?.acquisition.organic_sessions ?? 0],
  ] as const

  return (
    <section className="admin-metric-grid" aria-label="Key metrics">
      {metrics.map(([Icon, label, value]) => (
        <article className="admin-metric" key={label}>
          <Icon size={18} aria-hidden="true" />
          <span>{label}</span>
          <strong>{formatAdminNumber(value)}</strong>
        </article>
      ))}
    </section>
  )
}

export function TrafficPanel({
  dashboard,
  isLoading,
  maxDailyVisits,
  trafficDays,
  onChangeDays,
}: {
  dashboard: AdminDashboard | null
  isLoading: boolean
  maxDailyVisits: number
  trafficDays: number
  onChangeDays: (days: number) => void
}) {
  return (
    <article className="admin-panel admin-panel-wide">
      <div className="admin-panel-head">
        <h2>Traffic</h2>
        <div className="admin-day-picker" role="group" aria-label="Traffic range">
          {TRAFFIC_DAY_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              className={option === trafficDays ? 'is-active' : ''}
              onClick={() => onChangeDays(option)}
              disabled={isLoading}
            >
              {option}d
            </button>
          ))}
        </div>
      </div>
      <div
        className={
          `admin-traffic-bars${
            trafficDays > DENSE_TRAFFIC_THRESHOLD ? ' admin-traffic-dense' : ''
          }`
        }
        style={{
          gridTemplateColumns: `repeat(${
            dashboard?.traffic.daily.length ?? trafficDays
          }, minmax(0, 1fr))`,
        }}
      >
        {dashboard?.traffic.daily.map((row) => (
          <div
            className="admin-traffic-day"
            key={row.date}
            title={`${row.date}: ${row.visits} visits, ${row.visitors} visitors`}
          >
            <div className="admin-bar-track">
              <span
                style={{
                  height: `${
                    Math.max(
                      MINIMUM_TRAFFIC_BAR_PERCENT,
                      (row.visits / maxDailyVisits) * 100,
                    )
                  }%`,
                }}
              />
            </div>
            <strong>{row.visits}</strong>
            <small>{row.date.slice(5)}</small>
          </div>
        ))}
      </div>
      <div className="admin-inline-stats">
        <span>
          {formatAdminNumber(dashboard?.traffic.total_visits ?? 0)} visits
        </span>
        <span>
          {formatAdminNumber(dashboard?.traffic.unique_visitors ?? 0)} visitors
        </span>
        <span>
          {formatAdminNumber(dashboard?.traffic.unique_ips ?? 0)} IPs
        </span>
        <span>
          {formatAdminNumber(dashboard?.traffic.unique_today ?? 0)} unique today
        </span>
      </div>
    </article>
  )
}

export function SummaryPanels({
  dashboard,
  health,
}: {
  dashboard: AdminDashboard | null
  health: AdminApiHealth
}) {
  return (
    <>
      <TopPagesPanel dashboard={dashboard} />
      <ApiHealthPanel health={health} />
      <AccountsPanel dashboard={dashboard} />
      <OrganicPanel dashboard={dashboard} />
      <SeoPanel dashboard={dashboard} />
    </>
  )
}

function TopPagesPanel({ dashboard }: { dashboard: AdminDashboard | null }) {
  return (
    <article className="admin-panel">
      <div className="admin-panel-head"><h2>Top Pages</h2></div>
      <div className="admin-row-list">
        {dashboard?.traffic.top_pages.length
          ? dashboard.traffic.top_pages.map((page) => (
              <div className="admin-row" key={page.path}>
                <span title={page.path}>{page.path}</span>
                <strong>{formatAdminNumber(page.visits)}</strong>
              </div>
            ))
          : <p className="admin-empty">No visits yet.</p>}
      </div>
    </article>
  )
}

function ApiHealthPanel({ health }: { health: AdminApiHealth }) {
  return (
    <article className="admin-panel">
      <div className="admin-panel-head"><h2>API Health</h2></div>
      <div className="admin-health-list">
        {Object.entries(health).map(([source, status]) => (
          <div className="admin-health-row" key={source}>
            <span className={`admin-dot ${adminHealthClass(status)}`} />
            <div>
              <strong>{source}</strong>
              <small title={status.message}>
                {status.message
                  ?? (status.configured ? status.status : 'not configured')}
              </small>
            </div>
            {status.latency_ms ? (
              <em>{Math.round(status.latency_ms)}ms</em>
            ) : null}
          </div>
        ))}
      </div>
    </article>
  )
}

function AccountsPanel({ dashboard }: { dashboard: AdminDashboard | null }) {
  return (
    <article className="admin-panel">
      <div className="admin-panel-head"><h2>Accounts</h2></div>
      <div className="admin-row-list">
        <AdminRow label="Registered" value={dashboard?.accounts.registered ?? 0} />
        <AdminRow label="Verified" value={dashboard?.accounts.verified ?? 0} />
        <AdminRow label="Active in 30 days" value={dashboard?.accounts.active_30d ?? 0} />
        <TextRow
          label="Signup conversion"
          value={`${(dashboard?.acquisition.signup_conversion ?? 0).toFixed(2)}%`}
        />
        <AdminRow
          label="Store outbound"
          value={dashboard?.acquisition.outbound_store_clicks ?? 0}
        />
        {Object.entries(dashboard?.acquisition.events ?? {}).map(
          ([event, count]) => (
            <AdminRow
              key={event}
              label={event.replaceAll('_', ' ')}
              value={count}
            />
          ),
        )}
      </div>
    </article>
  )
}

function OrganicPanel({ dashboard }: { dashboard: AdminDashboard | null }) {
  return (
    <article className="admin-panel">
      <div className="admin-panel-head"><h2>Organic Landing Pages</h2></div>
      <div className="admin-row-list">
        {dashboard?.acquisition.organic_landing_pages.length
          ? dashboard.acquisition.organic_landing_pages.map((page) => (
              <div className="admin-row" key={page.path}>
                <span title={page.path}>{page.path}</span>
                <strong>{formatAdminNumber(page.visits)}</strong>
              </div>
            ))
          : <p className="admin-empty">No Google referrals in this range.</p>}
        <AdminRow
          label="Repeat visitors"
          value={dashboard?.acquisition.repeat_visitors ?? 0}
        />
        <AdminRow
          label="Google visitors"
          value={dashboard?.acquisition.organic_visitors ?? 0}
        />
        <AdminRow
          label="Google signups"
          value={dashboard?.acquisition.organic_signups ?? 0}
        />
        <TextRow
          label="Google conversion"
          value={
            `${(dashboard?.acquisition.organic_signup_conversion ?? 0).toFixed(2)}%`
          }
        />
      </div>
    </article>
  )
}

function SeoPanel({ dashboard }: { dashboard: AdminDashboard | null }) {
  const exclusions = Object.entries(
    dashboard?.catalog.seo_exclusions ?? {},
  ).sort(([, left], [, right]) => right - left)
  return (
    <article className="admin-panel">
      <div className="admin-panel-head"><h2>SEO Exclusions</h2></div>
      <div className="admin-row-list">
        {exclusions.map(([reason, count]) => (
          <AdminRow
            key={reason}
            label={reason.replaceAll('_', ' ')}
            value={count}
          />
        ))}
      </div>
    </article>
  )
}

function DataFillActions({
  dataFill,
  isStartingDataFill,
  isStartingPrimaryScores,
  onStartDataFill,
  onStartPrimaryScores,
}: Pick<
  DataFillPanelProps,
  | 'dataFill'
  | 'isStartingDataFill'
  | 'isStartingPrimaryScores'
  | 'onStartDataFill'
  | 'onStartPrimaryScores'
>) {
  return (
    <div className="admin-panel-actions">
      <button type="button" onClick={onStartPrimaryScores} disabled={isStartingPrimaryScores || dataFill?.running}>
        <RefreshCw size={15} aria-hidden="true" />
        <span>{isStartingPrimaryScores ? 'Starting' : dataFill?.running ? 'Running' : 'Fill 4 scores'}</span>
      </button>
      <button type="button" onClick={onStartDataFill} disabled={isStartingDataFill || dataFill?.running}>
        <RefreshCw size={15} aria-hidden="true" />
        <span>{isStartingDataFill ? 'Starting' : dataFill?.running ? 'Running' : 'Run fill'}</span>
      </button>
    </div>
  )
}

function DataFillBudgets({
  dataFill,
  primaryScoreRows,
  rateLimitRows,
}: Pick<DataFillPanelProps, 'dataFill' | 'primaryScoreRows' | 'rateLimitRows'>) {
  return (
    <div className="admin-budget-list">
      {primaryScoreRows.map(([source, coverage]) => (
        <TextRow
          key={`coverage-${source}`}
          label={`${source} live`}
          value={`${formatAdminNumber(coverage.live)}/${formatAdminNumber(dataFill?.primary_scores.total_games ?? 0)}`}
        />
      ))}
      {rateLimitRows.map(([source, budget]) => {
        const percentage = budget.limit > 0
          ? (budget.remaining / budget.limit) * 100
          : 0
        return (
          <div className="admin-budget-row" key={source}>
            <span>{source}</span>
            <div className="admin-budget-track">
              <i style={{ width: `${Math.max(MINIMUM_BUDGET_BAR_PERCENT, percentage)}%` }} />
            </div>
            <strong>{budget.remaining}/{budget.limit}</strong>
          </div>
        )
      })}
    </div>
  )
}

interface DataFillPanelProps {
  dataFill: DataFillStatus | null
  dataGaps: readonly (readonly [string, number])[]
  isStartingDataFill: boolean
  isStartingPrimaryScores: boolean
  primaryScoreRows: [string, PrimaryScoreCoverage['sources'][string]][]
  rateLimitRows: [string, { remaining: number; limit: number }][]
  onStartDataFill: () => void
  onStartPrimaryScores: () => void
}

export function DataFillPanel({
  dataFill,
  dataGaps,
  isStartingDataFill,
  isStartingPrimaryScores,
  primaryScoreRows,
  rateLimitRows,
  onStartDataFill,
  onStartPrimaryScores,
}: DataFillPanelProps) {
  return (
    <article className="admin-panel admin-panel-wide">
      <div className="admin-panel-head">
        <h2>Data Fill</h2>
        <DataFillActions
          dataFill={dataFill}
          isStartingDataFill={isStartingDataFill}
          isStartingPrimaryScores={isStartingPrimaryScores}
          onStartDataFill={onStartDataFill}
          onStartPrimaryScores={onStartPrimaryScores}
        />
      </div>
      <div className="admin-data-fill-grid">
        <div className="admin-row-list">
          <AdminRow
            label="Total games"
            value={dataFill?.catalog.total_games ?? 0}
          />
          <TextRow
            label="4-source complete"
            value={
              `${formatAdminNumber(dataFill?.primary_scores.complete_games ?? 0)}`
              + '/'
              + `${formatAdminNumber(dataFill?.primary_scores.total_games ?? 0)}`
            }
          />
          {dataGaps.map(([label, value]) => (
            <AdminRow key={label} label={label} value={value} />
          ))}
        </div>
        <DataFillBudgets
          dataFill={dataFill}
          primaryScoreRows={primaryScoreRows}
          rateLimitRows={rateLimitRows}
        />
      </div>
      <div className="admin-inline-stats">
        <span>Last run: {dataFill?.last_run?.status ?? 'none'}</span>
        {dataFill?.last_run?.finished_at ? (
          <span>{formatAdminDateTime(dataFill.last_run.finished_at)}</span>
        ) : null}
      </div>
    </article>
  )
}

export function ScoreAndCatalogPanels({
  dashboard,
  token,
  onScoreWeightsSaved,
}: {
  dashboard: AdminDashboard | null
  token: string
  onScoreWeightsSaved: () => void
}) {
  return (
    <>
      <article className="admin-panel admin-panel-wide">
        <div className="admin-panel-head"><h2>Score Weights</h2></div>
        <ScoreWeightSettings token={token} onSaved={onScoreWeightsSaved} />
      </article>
      <article className="admin-panel">
        <div className="admin-panel-head"><h2>Score Data</h2></div>
        <RefreshAllPanel token={token} />
      </article>
      <article className="admin-panel">
        <div className="admin-panel-head">
          <h2>Catalog</h2>
          <Server size={16} aria-hidden="true" />
        </div>
        <div className="admin-row-list">
          <AdminRow
            label="Non-game rows"
            value={dashboard?.catalog.non_game_rows ?? 0}
          />
          <AdminRow
            label="Rating snapshots"
            value={dashboard?.catalog.rating_snapshots ?? 0}
          />
          <AdminRow
            label="Source snapshots"
            value={dashboard?.catalog.source_snapshots ?? 0}
          />
        </div>
      </article>
    </>
  )
}

export function ActivityPanels({
  auditLogs,
  auditOnlyFailures,
  dashboard,
  onToggleAuditFailures,
}: {
  auditLogs: AdminAuditLog[]
  auditOnlyFailures: boolean
  dashboard: AdminDashboard | null
  onToggleAuditFailures: () => void
}) {
  return (
    <>
      <RecentVisitsPanel dashboard={dashboard} />
      <RecentIpsPanel dashboard={dashboard} />
      <AuditPanel
        auditLogs={auditLogs}
        onlyFailures={auditOnlyFailures}
        onToggleFailures={onToggleAuditFailures}
      />
    </>
  )
}

function RecentVisitsPanel({ dashboard }: { dashboard: AdminDashboard | null }) {
  return (
    <article className="admin-panel admin-panel-wide">
      <div className="admin-panel-head">
        <h2>Recent Visits</h2>
        <Activity size={16} aria-hidden="true" />
      </div>
      <div className="admin-visit-table">
        {dashboard?.traffic.recent_visits.length
          ? dashboard.traffic.recent_visits.map((visit) => (
              <div
                className="admin-visit-row"
                key={`${visit.created_at}-${visit.visitor}-${visit.path}`}
                title={visit.user_agent ?? visit.referrer ?? undefined}
              >
                <span>{formatAdminDateTime(visit.created_at)}</span>
                <strong title={visit.path}>{visit.path}</strong>
                <em>{visit.ip ?? `#${visit.ip_fingerprint ?? 'unknown'}`}</em>
                <small title={visit.account ?? undefined}>
                  {visit.account
                    ?? visit.country
                    ?? visit.timezone
                    ?? visit.language
                    ?? visit.screen
                    ?? 'anonymous'}
                </small>
              </div>
            ))
          : <p className="admin-empty">No visits recorded.</p>}
      </div>
    </article>
  )
}

function RecentIpsPanel({ dashboard }: { dashboard: AdminDashboard | null }) {
  return (
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
        {dashboard?.traffic.recent_ips.length
          ? dashboard.traffic.recent_ips.map((entry) => (
              <div className="admin-ip-row" key={entry.fingerprint}>
                <strong>{entry.ip ?? `#${entry.fingerprint}`}</strong>
                <span>{entry.country ?? 'unknown'}</span>
                <em>{formatAdminNumber(entry.visits)} visits</em>
                <small>{formatAdminDateTime(entry.first_seen)}</small>
                <small>{formatAdminDateTime(entry.last_seen)}</small>
              </div>
            ))
          : <p className="admin-empty">No visitor IPs recorded.</p>}
      </div>
    </article>
  )
}

function AuditPanel({
  auditLogs,
  onlyFailures,
  onToggleFailures,
}: {
  auditLogs: AdminAuditLog[]
  onlyFailures: boolean
  onToggleFailures: () => void
}) {
  return (
    <article className="admin-panel admin-panel-full">
      <div className="admin-panel-head">
        <h2>Admin Activity</h2>
        <button
          type="button"
          className={
            onlyFailures
              ? 'admin-audit-filter is-active'
              : 'admin-audit-filter'
          }
          onClick={onToggleFailures}
        >
          <ScrollText size={14} aria-hidden="true" />
          <span>{onlyFailures ? 'Failures only' : 'All requests'}</span>
        </button>
      </div>
      <div className="admin-audit-table">
        {auditLogs.length
          ? auditLogs.map((entry) => (
              <div
                className={
                  entry.success
                    ? 'admin-audit-row'
                    : 'admin-audit-row is-failure'
                }
                key={entry.id}
                title={entry.user_agent ?? undefined}
              >
                <span>{formatAdminDateTime(entry.created_at)}</span>
                <strong>{entry.username ?? 'anonymous'}</strong>
                <em>{entry.action === 'login' ? 'login' : entry.method}</em>
                <small
                  title={entry.query ? `${entry.path}?${entry.query}` : entry.path}
                >
                  {entry.path}
                </small>
                <span className="admin-audit-status">{entry.status_code}</span>
                <small>{entry.ip_address ?? 'unknown'}</small>
              </div>
            ))
          : <p className="admin-empty">No admin activity recorded.</p>}
      </div>
    </article>
  )
}

function AdminRow({ label, value }: { label: string; value: number }) {
  return <TextRow label={label} value={formatAdminNumber(value)} />
}

function TextRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="admin-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}
